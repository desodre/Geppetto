from __future__ import annotations

import subprocess
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import cast

from uiautomator2 import Device as U2Device

from ._logging import DeviceLogger
from .core.adb import AdbClient, wait_for_boot
from .core.fastboot import FastbootClient
from .exceptions import DeviceTimeoutError, WidgetNotFoundError
from .models.by import By
from .recording import ScreenRecording
from .services.lockscreen import LockscreenService
from .services.notification import NotificationService
from .services.wifi import WifiService
from .ui.bounds import Bounds
from .ui.widget import Widget
from .ui.window_dump import WindowDump


class Device:
    """High-level Android device controller.

    Uses **composition** to combine ADB transport, Fastboot transport,
    UIAutomator2, and device services (WiFi, Lockscreen, Notification)
    into a single ergonomic API.

    Example::

        device = Device("SERIAL123")
        device.install("app.apk", replace=True)
        widget = device.await_widget(By.TEXT, "Login")
        device.click(widget)
    """

    class BluetoothAction(Enum):
        ENABLE = "enable"
        DISABLE = "disable"

    #: Folders inside :attr:`result_path` where captured media is saved.
    SCREENSHOTS_DIR = Path("Images") / "Screenshots"
    SCREENRECORDS_DIR = Path("Videos") / "Screenrecords"
    #: Where media is written on the device before being pulled.
    DEVICE_MEDIA_DIR = "/sdcard/DCIM/Geppetto"

    def __init__(
        self,
        serial: str,
        output_dir: str | Path = "./results",
        *,
        log_to_console: bool = True,
        log_to_file: bool = True,
    ) -> None:
        """Connect to the device *serial*.

        Raises:
            DeviceNotFoundError: When the device does not answer adb.
        """
        self._serial = serial

        # ── Transport Layers ─────────────────────────────────────────
        self.adb = AdbClient(serial)
        self.fastboot = FastbootClient(serial)
        self._u2 = U2Device(serial=serial)

        # ── Result Directory Setup ───────────────────────────────────
        run_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.result_path = Path(output_dir) / f"{run_ts}_{serial}"
        for folder in (self.SCREENSHOTS_DIR, self.SCREENRECORDS_DIR, Path("Logs")):
            (self.result_path / folder).mkdir(parents=True, exist_ok=True)

        # ── Logger ───────────────────────────────────────────────────
        effective_serial = self.adb.real_serial or serial
        log_dir = self.result_path if log_to_file else None
        self.logger = DeviceLogger.get_logger(
            effective_serial, "Device", result_dir=log_dir, log_to_console=log_to_console
        )
        # Also configure the ADB transport logger to write to result dir
        self.adb.logger = DeviceLogger.get_logger(
            effective_serial, "ADB", result_dir=log_dir, log_to_console=log_to_console
        )
        if self.adb.real_serial != serial:
            self.logger.warning(
                "Provided serial (%s) differs from device serial (%s).",
                serial,
                self.adb.real_serial,
            )

        # ── Services ─────────────────────────────────────────────────
        self.lockscreen = LockscreenService(self.adb)
        self.wifi = WifiService(self.adb)
        self.notification = NotificationService(self.adb)

    def __str__(self) -> str:
        return self._serial

    # ── Device Properties ────────────────────────────────────────────

    @property
    def serial(self) -> str:
        return self._serial

    @property
    def log_path(self) -> Path:
        return self.result_path

    @property
    def screen_size(self) -> tuple[int, int]:
        return cast(tuple[int, int], self._u2.window_size())

    @property
    def bluetooth_address(self) -> str:
        return self.adb.shell("settings get secure bluetooth_address").strip()

    @property
    def bluetooth_name(self) -> str:
        return self.adb.shell("settings get secure bluetooth_name").strip()

    @property
    def is_wifi_debugged(self) -> bool:
        return self._serial != self.adb.real_serial

    # ── Device Info Queries ──────────────────────────────────────────

    def get_os(self) -> str:
        """Android release (e.g. ``"14"``), from ``ro.build.version.release``."""
        return self.adb.shell("getprop ro.build.version.release").strip()

    def get_activity(self) -> str | None:
        raw = self.adb.shell("dumpsys activity activities")
        for line in raw.splitlines():
            if "topResumedActivity" in line or "mResumedActivity" in line:
                try:
                    return line.split("{")[1].split("}")[0].split()[-1]
                except (IndexError, ValueError):
                    pass
        return None

    def has_connection(self) -> bool:
        output = self.adb.shell("ping -c 1 google.com")
        return "1 received" in output or "1 packets received" in output

    def has_sim_card(self) -> bool:
        states = self.adb.shell("getprop gsm.sim.state").strip().split(",")
        return any(s in ("READY", "LOADED") for s in states)

    def is_installed(self, package_name: str) -> bool:
        """Exact match: ``com.app`` is not reported installed because ``com.app.debug`` is."""
        output = self.adb.shell(["pm", "list", "packages", package_name])
        return f"package:{package_name}" in output.split()

    # ── App Management ───────────────────────────────────────────────

    def install(
        self,
        path_app: str,
        *,
        all_runtime_permissions: bool = False,
        test_app: bool = False,
        allow_downgrade: bool = False,
        instant: bool = False,
        replace: bool = False,
        bypass_low_target_sdk_block: bool = False,
    ) -> str:
        flags: list[str] = []
        if all_runtime_permissions:
            flags.append("-g")
        if test_app:
            flags.append("-t")
        if allow_downgrade:
            flags.append("-d")
        if instant:
            flags.append("--instant")
        if replace:
            flags.append("-r")
        if bypass_low_target_sdk_block:
            flags.append("--bypass-low-target-sdk-block")

        self.logger.info("Installing %s (flags: %s)", path_app, flags or "none")
        return self.adb.cmd(["install", *flags, str(path_app)])

    def open_activity(self, activity: str) -> str:
        self.logger.info("Opening activity: %s", activity.split("/")[-1])
        return self.adb.shell(["am", "start", "-n", activity])

    def open_app(self, package: str) -> str:
        self.logger.info("Opening: %s", package)
        return self.adb.shell(
            ["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"]
        )

    def kill_app(self, package_name: str) -> None:
        self.logger.info("Killing app: %s", package_name)
        self.adb.shell(["am", "force-stop", package_name])

    # ── UI Interaction ───────────────────────────────────────────────

    def click(self, target: tuple[float, float] | Widget | Bounds) -> None:
        match target:
            case Widget():
                if target.bounds is None:
                    raise ValueError("Widget has no bounds")
                x, y = target.bounds.center
            case Bounds():
                x, y = target.center
            case (x, y):
                pass
            case _:
                raise TypeError("target must be a Widget, Bounds, or (x, y) tuple")
        self.adb.shell(f"input tap {x} {y}")
        self.logger.info("Click at (%.0f, %.0f)", x, y)

    def swipe(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        duration: float = 1000,
    ) -> None:
        self.logger.info("Swipe %s → %s (%dms)", start, end, duration)
        self.adb.shell(
            f"input touchscreen swipe {start[0]} {start[1]} {end[0]} {end[1]} {int(duration)}"
        )

    def swipe_by_bounds(
        self,
        start: Bounds,
        end: Bounds,
        duration: float = 1000,
    ) -> None:
        self.swipe(start.center, end.center, duration)

    def drag_and_drop(
        self,
        source: Bounds,
        dest: Bounds,
        duration: float = 1000,
    ) -> None:
        """Long-press *source* and drop it on *dest* (``input draganddrop``, Android 7+)."""
        self.logger.info("Drag %s → %s", source.center, dest.center)
        (x1, y1), (x2, y2) = source.center, dest.center
        self.adb.shell(["input", "draganddrop", x1, y1, x2, y2, int(duration)])

    def input_text(self, text: str, *, log_text: bool = True) -> None:
        """Type *text* into the focused field.

        ``input text`` reads ``%s`` as a space and stops at a raw space, so spaces are
        encoded; every other character goes quoted for the device shell. Pass
        ``log_text=False`` for passwords and other secrets.
        """
        self.logger.info("Input text: %s", text if log_text else "<hidden>")
        self.adb.shell(["input", "text", text.replace(" ", "%s")])

    def key_event(self, keycode: int) -> None:
        self.logger.info("Key event: %d", keycode)
        self.adb.shell(f"input keyevent {keycode}")

    def fast_app_swipe(self) -> None:
        self.key_event(187)  # KEYCODE_APP_SWITCH
        time.sleep(1)
        self.key_event(187)

    # ── UI Hierarchy ─────────────────────────────────────────────────

    def get_window_dump(self) -> WindowDump:
        return WindowDump(self._u2.dump_hierarchy())

    def await_widget(
        self,
        by: By,
        value: str,
        timeout: int = 10,
    ) -> Widget:
        """Wait up to *timeout* seconds for a widget matching *by*/*value*.

        Raises:
            DeviceTimeoutError: When the widget doesn't appear in time.
        """
        selector_map = {
            By.TEXT: "text",
            By.ID: "resourceId",
            By.CLASS: "className",
            By.CONTENT_DESC: "description",
        }
        if by is By.XPATH:
            # Poll our own dump: uiautomator2's XPath engine names elements by class
            # (//android.widget.TextView) while WindowDump keeps the raw <node> tags, so the same
            # expression must be evaluated by the same engine that find_widget uses.
            deadline = time.monotonic() + timeout
            while True:
                try:
                    return self.get_window_dump().find_widget(by, value)
                except WidgetNotFoundError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.5)
            appeared = False
        elif by in selector_map:
            appeared = bool(self._u2(**{selector_map[by]: value}).wait(timeout=timeout))
        else:
            raise ValueError(f"Unsupported By strategy: {by}")

        if appeared:
            return self.get_window_dump().find_widget(by, value)
        raise DeviceTimeoutError(f"Timeout after {timeout}s waiting for {by.name}={value}")

    # ── Activity Wait ────────────────────────────────────────────────

    def await_for_activity(self, activity: str, timeout: int = 10) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if activity in self.adb.shell("dumpsys activity activities"):
                return True
            time.sleep(1)
            self.logger.info("Waiting for activity: %s", activity)
        self.logger.warning("Activity %s not found within %ds", activity, timeout)
        return False

    # ── Media Capture ────────────────────────────────────────────────

    def _media_name(self, name: str, ext: str) -> str:
        if not name:
            name = self.get_activity() or datetime.now().strftime("%Y%m%d_%H%M%S")
            name = name.replace("/", "_")
        return f"{name}.{ext}"

    def screenshot(self, name: str = "", pull_to_results: bool = False) -> str:
        """Capture the screen. Returns the device path, or the local path when pulled
        (saved under ``<result_path>/Images/Screenshots``). Without *name*, the current
        activity (or a timestamp) names the file."""
        file_name = self._media_name(name, "png")

        if pull_to_results:
            local_path = self.result_path / self.SCREENSHOTS_DIR / file_name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(self.adb.exec_out("screencap -p"))
            return str(local_path)

        device_path = f"{self.DEVICE_MEDIA_DIR}/{file_name}"
        self.adb.mkdir(self.DEVICE_MEDIA_DIR)
        self.adb.shell(["screencap", "-p", device_path])
        return device_path

    async def record_screen(
        self,
        name: str = "",
        duration: int = 180,
        pull_to_results: bool = False,
    ) -> str:
        """Record the screen for *duration* seconds (Android caps it at 180). Returns the
        device path, or the local path under ``<result_path>/Videos/Screenrecords``."""
        file_name = self._media_name(name, "mp4")
        device_path = f"{self.DEVICE_MEDIA_DIR}/{file_name}"
        self.adb.mkdir(self.DEVICE_MEDIA_DIR)
        await self.adb.async_shell(["screenrecord", "--time-limit", duration, device_path])

        if pull_to_results:
            local_dir = self.result_path / self.SCREENRECORDS_DIR
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = self.adb.pull(device_path, local_dir)
            self.adb.rm(device_path)
            return local_path
        return device_path

    # ── Logcat ───────────────────────────────────────────────────────

    def clear_logcat(self) -> None:
        """Empty the device log buffers (``logcat -c``)."""
        self.adb.shell("logcat -c")

    def dump_logcat(self, *, fmt: str = "threadtime") -> str:
        """Everything in the log buffers right now (``logcat -d``), in format *fmt*."""
        return self.adb.shell(["logcat", "-d", "-v", fmt])

    def start_recording(self, name: str = "", time_limit: int = 180) -> ScreenRecording:
        """Start recording the screen in the background; finish it with
        ``stop(save_to)`` or ``discard()``. Android caps recordings at 180 s."""
        return ScreenRecording(self.adb, self._media_name(name, "mp4")[:-4], time_limit).start()

    # ── Phone & Bluetooth ────────────────────────────────────────────

    def make_call(self, number: str) -> str:
        self.logger.info("Making call to: %s", number)
        return self.adb.shell(
            ["am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{number}"]
        )

    def bluetooth_manager(self, action: BluetoothAction) -> str:
        return self.adb.shell(["cmd", "bluetooth_manager", action.value])

    # ── Filesystem ───────────────────────────────────────────────────

    def list_directories(self, path: str, real_path: bool = False) -> list[str]:
        """Entries (files and folders) in *path* on the device; with *real_path*, as
        full paths."""
        ls = self.adb.shell(["ls", path])
        lines = ls.splitlines()
        if real_path:
            return [f"{path}/{p}" for p in lines]
        return lines

    # ── Device Lifecycle ─────────────────────────────────────────────

    def reboot(self, option: str | None = None, timeout: int = 180) -> None:
        """Reboot and wait until Android reports ``sys.boot_completed=1``.

        Raises:
            DeviceTimeoutError: When the boot does not complete within *timeout* seconds.
        """
        try:
            self.adb.shell(["reboot", option] if option else "reboot")
        except subprocess.CalledProcessError:
            pass  # Expected — device disconnects
        self.logger.info("Rebooting device…")
        self.adb.wait_for_device()
        self.wait_for_boot(timeout)
        self.logger.info("Device rebooted")

    def wait_for_boot(self, timeout: int = 180) -> None:
        """Block until ``sys.boot_completed`` is ``1``.

        Raises:
            DeviceTimeoutError: When it does not happen within *timeout* seconds.
        """
        wait_for_boot(self.adb, timeout)

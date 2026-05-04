from __future__ import annotations

import os
import shlex
import subprocess
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, cast

from uiautomator2 import Device as U2Device

if TYPE_CHECKING:
    pass

from ._logging import DeviceLogger
from .core.adb import AdbClient
from .core.fastboot import FastbootClient
from .exceptions import DeviceTimeoutError
from .models.by import By
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

    def __init__(self, serial: str, output_dir: str | Path = "./results") -> None:
        self._serial = serial

        # ── Transport Layers ─────────────────────────────────────────
        self.adb = AdbClient(serial)
        self.fastboot = FastbootClient(serial)
        self._u2 = U2Device(serial=serial)

        # ── Result Directory Setup ───────────────────────────────────
        run_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.result_path = Path(output_dir) / f"{run_ts}_{serial}"
        os.makedirs(self.result_path / "Images" / "Screenshots", exist_ok=True)
        os.makedirs(self.result_path / "Images" / "Pictures", exist_ok=True)
        os.makedirs(self.result_path / "Logs", exist_ok=True)

        # ── Logger ───────────────────────────────────────────────────
        effective_serial = self.adb.real_serial if self.adb.real_serial != serial else serial
        self.logger = DeviceLogger.get_logger(
            effective_serial,
            "Device",
            result_dir=self.result_path,
        )
        # Also configure the ADB transport logger to write to result dir
        self.adb.logger = DeviceLogger.get_logger(
            effective_serial,
            "ADB",
            result_dir=self.result_path,
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
        return self.adb.shell("getprop ro.system_ext.build.version.release_or_codename").strip()

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
        return package_name in self.adb.shell(f"pm list packages {package_name}")

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

        cmd = f"install {' '.join(flags)} {path_app}" if flags else f"install {path_app}"
        self.logger.info("Installing %s (flags: %s)", path_app, flags or "none")
        return self.adb.cmd(cmd)

    def open_activity(self, activity: str) -> str:
        self.logger.info("Opening activity: %s", activity.split("/")[-1])
        return self.adb.shell(f"am start -n {activity}")

    def open_app(self, package: str) -> str:
        self.logger.info("Opening: %s", package)
        return self.adb.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")

    def kill_app(self, package_name: str) -> None:
        self.logger.info("Killing app: %s", package_name)
        self.adb.shell(f"am force-stop {package_name}")

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
        self.logger.info("Drag %s → %s", source.center, dest.center)
        self.adb.shell(
            f"input swipe {source.center[0]} {source.center[1]} "
            f"{dest.center[0]} {dest.center[1]} {int(duration)}"
        )

    def input_text(self, text: str) -> None:
        self.logger.info("Input text: %s", text)
        self.adb.shell(f"input text {shlex.quote(text)}")

    def key_event(self, keycode: int) -> None:
        self.logger.info("Key event: %d", keycode)
        self.adb.shell(f"input keyevent {keycode}")

    def fast_app_swipe(self) -> None:
        self.key_event(187)  # KEYCODE_APP_SWITCH
        sleep(1)
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
            By.TEXT: {"text": value},
            By.ID: {"resourceId": value},
            By.CLASS: {"className": value},
            By.CONTENT_DESC: {"description": value},
            By.XPATH: {"xpath": value},
        }
        if by not in selector_map:
            raise ValueError(f"Unsupported By strategy: {by}")

        selector = self._u2(**selector_map[by])
        if selector.wait(timeout=timeout):
            return self.get_window_dump().find_widget(by, value)
        raise DeviceTimeoutError(f"Timeout after {timeout}s waiting for {by.name}={value}")

    # ── Activity Wait ────────────────────────────────────────────────

    def await_for_activity(self, activity: str, timeout: int = 10) -> bool:
        start = datetime.now()
        while (datetime.now() - start).seconds < timeout:
            if activity in self.adb.shell("dumpsys activity activities"):
                return True
            time.sleep(1)
            self.logger.info("Waiting for activity: %s", activity)
        self.logger.warning("Activity %s not found within %ds", activity, timeout)
        return False

    # ── Media Capture ────────────────────────────────────────────────

    def _media_paths(self, name: str, ext: str, subfolder: str) -> tuple[Path, str]:
        if not name:
            name = self.get_activity() or datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.result_path / subfolder, f"{name}.{ext}"

    def screenshot(self, name: str, pull_to_results: bool = False) -> str:
        result_dir, file_name = self._media_paths(name, "png", "Screenshots")
        device_dir = "/sdcard/DCIM/Geppetto"
        device_path = f"{device_dir}/{file_name}"
        self.adb.shell(f"mkdir -p {device_dir}")

        if pull_to_results:
            os.makedirs(result_dir, exist_ok=True)
            local_path = result_dir / file_name
            with open(local_path, "wb") as f:
                subprocess.run(
                    ["adb", "-s", self._serial, "exec-out", "screencap", "-p"],
                    stdout=f,
                    check=True,
                )
            return str(local_path)

        self.adb.shell(f"screencap -p {device_path}")
        return device_path

    async def record_screen(
        self,
        name: str,
        duration: int = 180,
        pull_to_results: bool = False,
    ) -> str:
        result_dir, file_name = self._media_paths(name, "mp4", "Screenrecords")
        device_dir = "/sdcard/DCIM/Geppetto"
        device_path = f"{device_dir}/{file_name}"
        self.adb.shell(f"mkdir -p {device_dir}")

        if pull_to_results:
            os.makedirs(result_dir, exist_ok=True)
            await self.adb.async_shell(f"screenrecord --time-limit {duration} {device_path}")
            self.adb.pull(device_path, str(result_dir / file_name))
            self.adb.rm(device_path)
            return str(result_dir / file_name)

        await self.adb.async_shell(f"screenrecord --time-limit {duration} {device_path}")
        return device_path

    # ── Phone & Bluetooth ────────────────────────────────────────────

    def make_call(self, number: str) -> str:
        self.logger.info("Making call to: %s", number)
        return self.adb.shell(f"am start -a android.intent.action.CALL -d tel:{number}")

    def bluetooth_manager(self, action: BluetoothAction) -> str:
        return self.adb.shell(f"cmd bluetooth_manager {action.value}")

    # ── Filesystem ───────────────────────────────────────────────────

    def list_directories(self, path: str, real_path: bool = False) -> list[str]:
        ls = self.adb.shell(f"ls {path}")
        lines = ls.splitlines()
        if real_path:
            return [f"{path}/{p}" for p in lines]
        return lines

    # ── Device Lifecycle ─────────────────────────────────────────────

    def reboot(self, option: str | None = None) -> None:
        try:
            self.adb.shell(f"reboot {option}" if option else "reboot")
        except subprocess.CalledProcessError:
            pass  # Expected — device disconnects
        self.logger.info("Rebooting device…")
        self.adb.wait_for_device()
        time.sleep(10)
        self.logger.info("Device rebooted")

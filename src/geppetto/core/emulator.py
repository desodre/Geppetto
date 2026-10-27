"""Android emulator: find the SDK, list AVDs, start/stop and snapshots."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from ..exceptions import DeviceNotFoundError, DeviceTimeoutError, EmulatorError
from . import host
from .adb import AdbClient, wait_for_boot


def sdk_root() -> Path | None:
    """The Android SDK: ``ANDROID_SDK_ROOT``/``ANDROID_HOME``, then the default install places."""
    candidates = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")]
    home = Path.home()
    if sys.platform == "darwin":
        candidates.append(str(home / "Library" / "Android" / "sdk"))
    elif sys.platform == "win32":
        candidates.append(str(Path(os.environ.get("LOCALAPPDATA", home)) / "Android" / "Sdk"))
    else:
        candidates.append(str(home / "Android" / "Sdk"))
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def emulator_binary() -> Path:
    """The ``emulator`` executable (PATH first, then ``<sdk>/emulator/``).

    Raises:
        EmulatorError: When it cannot be found.
    """
    on_path = shutil.which("emulator")
    if on_path:
        return Path(on_path)
    root = sdk_root()
    if root is not None:
        name = "emulator.exe" if sys.platform == "win32" else "emulator"
        binary = root / "emulator" / name
        if binary.exists():
            return binary
    raise EmulatorError(
        "Android emulator not found: install it with the SDK Manager and set ANDROID_SDK_ROOT"
    )


def list_avds() -> list[str]:
    """Names of the AVDs (virtual devices) created on this machine."""
    output = subprocess.run(
        [str(emulator_binary()), "-list-avds"], capture_output=True, text=True, check=True
    ).stdout
    # The emulator may print INFO/WARNING lines before the names.
    return [line.strip() for line in output.splitlines() if line.strip() and "|" not in line]


def avd_name(serial: str) -> str:
    """The AVD an ``emulator-NNNN`` serial is running (``adb emu avd name``)."""
    output = host.run_adb("-s", serial, "emu", "avd", "name")
    return output.splitlines()[0].strip() if output else ""


def running() -> dict[str, str]:
    """Running emulators: serial → AVD name."""
    return {e.serial: avd_name(e.serial) for e in host.devices() if e.is_emulator and e.ready}


def start(
    avd: str,
    *,
    headless: bool = False,
    snapshot: str | None = None,
    wipe_data: bool = False,
    extra_args: Sequence[str] = (),
    wait: bool = True,
    timeout: float = 300,
) -> str:
    """Start *avd* and return its serial (``emulator-5554``…).

    With *wait* (default) returns only when Android finished booting. The emulator keeps running
    after this process exits; its output goes to a log file in the temp folder.

    Raises:
        EmulatorError: Unknown AVD, or the emulator exited while starting.
        DeviceTimeoutError: No device or no boot within *timeout* seconds.
    """
    avds = list_avds()
    if avd not in avds:
        raise EmulatorError(f"AVD {avd!r} does not exist. Available: {', '.join(avds) or 'none'}")

    args = [str(emulator_binary()), "-avd", avd]
    if headless:
        args += ["-no-window", "-no-audio"]
    if snapshot:
        args += ["-snapshot", snapshot]
    if wipe_data:
        args.append("-wipe-data")
    args += list(extra_args)

    already = {e.serial for e in host.devices() if e.is_emulator}
    log_path = Path(tempfile.gettempdir()) / f"geppetto-emulator-{avd}.log"
    with open(log_path, "wb") as log:
        process = subprocess.Popen(
            args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )

    deadline = time.monotonic() + timeout
    serial = ""
    while time.monotonic() < deadline and not serial:
        if process.poll() is not None:
            tail = log_path.read_text(errors="replace")[-1500:]
            raise EmulatorError(f"Emulator for {avd!r} exited ({process.returncode}):\n{tail}")
        for entry in host.devices():
            if entry.is_emulator and entry.serial not in already and entry.ready:
                serial = entry.serial
                break
        else:
            time.sleep(2)
    if not serial:
        raise DeviceTimeoutError(f"Emulator {avd!r} did not appear in adb within {timeout}s")
    if wait:
        wait_for_boot(_reach(serial, deadline), max(1.0, deadline - time.monotonic()))
    return serial


def _reach(serial: str, deadline: float) -> AdbClient:
    """An AdbClient for a booting emulator: early in the boot adb lists it as ``device`` but the
    shell still closes the connection (``error: closed``), so retry until *deadline*."""
    while True:
        try:
            return AdbClient(serial)
        except DeviceNotFoundError as e:
            if time.monotonic() >= deadline:
                raise DeviceTimeoutError(f"Emulator {serial} never accepted adb shell: {e}") from e
            time.sleep(2)


def stop(serial: str) -> None:
    """Shut down a running emulator (``adb -s <serial> emu kill``)."""
    if not serial.startswith("emulator-"):
        raise EmulatorError(f"{serial} is not an emulator")
    if serial not in {e.serial for e in host.devices()}:
        raise EmulatorError(f"{serial} is not running (see `geppetto emulator list`)")
    host.run_adb("-s", serial, "emu", "kill")


def snapshot_save(serial: str, name: str) -> str:
    return host.run_adb("-s", serial, "emu", "avd", "snapshot", "save", name, timeout=120)


def snapshot_load(serial: str, name: str) -> str:
    return host.run_adb("-s", serial, "emu", "avd", "snapshot", "load", name, timeout=120)


def snapshot_list(serial: str) -> str:
    return host.run_adb("-s", serial, "emu", "avd", "snapshot", "list")

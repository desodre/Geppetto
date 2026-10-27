"""Environment checks behind ``geppetto doctor``: every problem comes with how to fix it."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum

from .core import emulator, host
from .exceptions import GeppettoError

#: Where uiautomator2 3.x keeps its agent on the device.
U2_AGENT = "/data/local/tmp/u2.jar"


class Status(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    INFO = "info"


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str
    fix: str = ""


def _run(*args: str) -> str:
    result = subprocess.run(list(args), capture_output=True, text=True, timeout=20)
    return (result.stdout + result.stderr).strip()


def check_python() -> Check:
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= (3, 12):
        return Check("Python", Status.OK, version)
    return Check("Python", Status.FAIL, version, "Geppetto needs Python 3.12 or newer.")


def check_adb() -> Check:
    path = host.adb_path()
    if path is None:
        return Check(
            "adb",
            Status.FAIL,
            "not found on PATH",
            "Install Android SDK Platform-Tools and add the platform-tools folder to PATH.",
        )
    version = _run(path, "version").splitlines()[0] if path else ""
    return Check("adb", Status.OK, f"{version} ({path})")


def check_fastboot() -> Check:
    path = shutil.which("fastboot")
    if path is None:
        return Check(
            "fastboot",
            Status.INFO,
            "not found on PATH",
            "Only needed for flashing (Device.fastboot); it ships with Platform-Tools.",
        )
    return Check("fastboot", Status.OK, path)


def check_devices(entries: list[host.DeviceEntry]) -> list[Check]:
    if not entries:
        return [
            Check(
                "devices",
                Status.WARN,
                "no device connected",
                "Connect a phone with USB debugging on (Settings › Developer options), "
                "pair one over Wi-Fi (`geppetto pair`) "
                "or start an emulator (`geppetto emulator start`).",
            )
        ]
    checks = []
    for entry in entries:
        name = f"device {entry.serial}"
        if entry.state == "unauthorized":
            checks.append(
                Check(
                    name,
                    Status.FAIL,
                    "unauthorized",
                    "Unlock the phone and accept the 'Allow USB debugging?' prompt "
                    "(revoke authorizations in Developer options if it does not show).",
                )
            )
        elif entry.state == "offline":
            checks.append(
                Check(
                    name,
                    Status.FAIL,
                    "offline",
                    "Replug the cable or run `adb kill-server && adb start-server`.",
                )
            )
        elif entry.state == "not found":
            checks.append(
                Check(
                    name, Status.FAIL, "not connected", "Check the serial with `geppetto devices`."
                )
            )
        elif not entry.ready:
            checks.append(
                Check(
                    name,
                    Status.FAIL,
                    entry.state,
                    "Run `adb kill-server` and reconnect the device.",
                )
            )
        else:
            checks += check_ready_device(entry)
    return checks


def check_ready_device(entry: host.DeviceEntry) -> list[Check]:
    name = f"device {entry.serial}"
    try:
        props = host.run_adb(
            "-s",
            entry.serial,
            "shell",
            "getprop sys.boot_completed; getprop ro.build.version.release; "
            f"getprop ro.product.model; ls {U2_AGENT} 2>/dev/null",
        )
    except GeppettoError as e:
        return [Check(name, Status.FAIL, f"adb shell failed: {e}", "Reconnect the device.")]
    lines = props.splitlines() + ["", "", "", ""]
    booted, release, model, agent = lines[0].strip(), lines[1].strip(), lines[2].strip(), lines[3]
    label = f"{model or entry.model or 'device'}, Android {release or '?'}"
    checks = []
    if booted == "1":
        checks.append(Check(name, Status.OK, label))
    else:
        checks.append(
            Check(
                name,
                Status.WARN,
                f"{label}, still booting",
                "Wait for the boot to finish (Device.wait_for_boot).",
            )
        )
    if U2_AGENT in agent:
        checks.append(Check(f"{name} uiautomator2", Status.OK, "agent installed"))
    else:
        checks.append(
            Check(
                f"{name} uiautomator2",
                Status.INFO,
                "agent not installed yet",
                "It is installed on the first Device(serial) connection "
                "(or run `python -m uiautomator2 init`).",
            )
        )
    return checks


def check_emulator() -> Check:
    try:
        binary = emulator.emulator_binary()
        avds = emulator.list_avds()
    except (GeppettoError, subprocess.CalledProcessError, OSError) as e:
        return Check(
            "emulator",
            Status.INFO,
            str(e).splitlines()[0],
            "Only needed for `geppetto emulator`; install it with the SDK Manager.",
        )
    if not avds:
        return Check(
            "emulator",
            Status.INFO,
            f"{binary} (no AVD created)",
            "Create one in Android Studio › Device Manager.",
        )
    return Check("emulator", Status.OK, f"{len(avds)} AVD(s): {', '.join(avds)}")


#: extra → modules it needs
EXTRAS = {
    "analyzers": ("PIL", "cv2", "imagehash", "extcolors", "numpy"),
    "hardware": ("brainstem",),
}


def check_extras() -> list[Check]:
    checks = []
    for extra, modules in EXTRAS.items():
        missing = [m for m in modules if importlib.util.find_spec(m) is None]
        if missing:
            checks.append(
                Check(
                    f"extra [{extra}]",
                    Status.INFO,
                    f"missing: {', '.join(missing)}",
                    f"pip install 'geppetto-android[{extra}]' if you need it.",
                )
            )
        else:
            checks.append(Check(f"extra [{extra}]", Status.OK, "installed"))
    return checks


def run_checks(serial: str | None = None) -> list[Check]:
    """Every check, in display order. With *serial*, only that device is inspected."""
    checks = [check_python(), check_adb()]
    if checks[-1].status is Status.OK:
        entries = host.devices()
        if serial is not None:
            entries = [e for e in entries if e.serial == serial] or [
                host.DeviceEntry(serial, "not found")
            ]
        checks += check_devices(entries)
    checks += [check_fastboot(), check_emulator(), *check_extras()]
    return checks

"""Host-side adb commands: the device list, Wi-Fi pairing and mDNS discovery.

Unlike :class:`~geppetto.core.adb.AdbClient`, nothing here targets one device.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

from ..exceptions import AdbCommandError, DeviceNotFoundError


def adb_path() -> str | None:
    """Full path of the ``adb`` binary on PATH, or ``None``."""
    return shutil.which("adb")


def run_adb(*args: str, timeout: float | None = 30) -> str:
    """Run ``adb <args>`` and return stdout (stderr appended: adb prints results on both).

    Raises:
        DeviceNotFoundError: When adb is not installed.
        AdbCommandError: When adb exits with an error or does not answer within *timeout*.
    """
    try:
        result = subprocess.run(
            ["adb", *args], capture_output=True, text=True, check=True, timeout=timeout
        )
    except FileNotFoundError as e:
        raise DeviceNotFoundError("adb is not installed or not on PATH") from e
    except subprocess.CalledProcessError as e:
        mensagem = ((e.stderr or "") + (e.stdout or "")).strip() or f"exit status {e.returncode}"
        raise AdbCommandError(f"adb {' '.join(args)}: {mensagem}") from e
    except subprocess.TimeoutExpired as e:
        raise AdbCommandError(f"adb {' '.join(args)}: no answer within {timeout}s") from e
    return (result.stdout + result.stderr).strip()


@dataclass(frozen=True)
class DeviceEntry:
    """One line of ``adb devices -l``."""

    serial: str
    state: str
    details: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        """adb can talk to it (state ``device``)."""
        return self.state == "device"

    @property
    def model(self) -> str:
        return self.details.get("model", "")

    @property
    def is_emulator(self) -> bool:
        return self.serial.startswith("emulator-")

    @property
    def is_wireless(self) -> bool:
        return ":" in self.serial or "._adb-tls-connect._tcp" in self.serial


def parse_devices(output: str) -> list[DeviceEntry]:
    entries = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or line.startswith(("List of devices", "*")):
            continue
        details = dict(p.split(":", 1) for p in parts[2:] if ":" in p)
        entries.append(DeviceEntry(parts[0], parts[1], details))
    return entries


def devices() -> list[DeviceEntry]:
    """Every device adb knows, ready or not (offline, unauthorized…)."""
    return parse_devices(run_adb("devices", "-l"))


@dataclass(frozen=True)
class MdnsService:
    """A service from ``adb mdns services`` (Wi-Fi debugging on Android 11+)."""

    name: str
    kind: str
    address: str

    @property
    def is_pairing(self) -> bool:
        return "pairing" in self.kind


def parse_mdns(output: str) -> list[MdnsService]:
    services = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1].startswith("_adb"):
            services.append(MdnsService(parts[0], parts[1].rstrip("."), parts[2]))
    return services


def mdns_services() -> list[MdnsService]:
    return parse_mdns(run_adb("mdns", "services"))


def _confirma(output: str, palavra: str, acao: str) -> str:
    if palavra not in output.lower():
        raise DeviceNotFoundError(f"adb {acao} failed: {output}")
    return output


def pair(address: str, code: str) -> str:
    """``adb pair <host:port> <code>`` (Android 11+ Wireless debugging).

    Raises:
        DeviceNotFoundError: When adb does not report success.
    """
    return _confirma(run_adb("pair", address, code, timeout=60), "successfully paired", "pair")


def connect(address: str) -> str:
    """``adb connect <host:port>``.

    Raises:
        DeviceNotFoundError: When adb does not report the connection.
    """
    return _confirma(run_adb("connect", address, timeout=60), "connected to", "connect")


def disconnect(address: str) -> str:
    return run_adb("disconnect", address)

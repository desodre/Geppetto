from __future__ import annotations

import asyncio
import logging
import posixpath
import shlex
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

from ..exceptions import DeviceIsSecureError, DeviceNotFoundError, DeviceTimeoutError

Command = str | Sequence[str | int | float]


def device_command(command: Command) -> str:
    """Build the single command line that ``adb shell`` hands to the device's ``sh``.

    ``adb shell`` joins its arguments with spaces and the device shell parses the result
    again, so running ``adb`` without ``shell=True`` only protects the *host*. A sequence
    is quoted argument by argument (each value reaches the device as one literal word,
    so ``;``, ``|`` or spaces in user data cannot run extra commands). A string is a
    trusted, already-written command line and is passed as is.
    """
    if isinstance(command, str):
        return command
    return " ".join(shlex.quote(str(arg)) for arg in command)


def list_devices() -> list[str]:
    """Serials of the devices ``adb devices`` reports as ready (state ``device``).

    Offline and unauthorized devices are left out. Raises :class:`DeviceNotFoundError` when the
    ``adb`` binary is missing.
    """
    try:
        output = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, check=True
        ).stdout
    except FileNotFoundError as e:
        raise DeviceNotFoundError("adb is not installed or not on PATH") from e
    serials = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


class AdbClient:
    """Low-level ADB transport layer.

    Provides synchronous and asynchronous methods for executing ADB commands on a
    specific device identified by its serial number. Pass user-supplied values as a
    sequence (``["am", "force-stop", package]``) so they are quoted for the device shell;
    see :func:`device_command`.

    Raises:
        DeviceNotFoundError: When the device does not answer ``adb shell`` on creation.
    """

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.logger = logging.getLogger(f"geppetto.adb.{serial}")
        try:
            self.real_serial: str = self.shell("getprop ro.serialno").strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            stderr = getattr(e, "stderr", "") or str(e)
            raise DeviceNotFoundError(
                f"Device {serial!r} is not reachable through adb: {stderr.strip()}"
            ) from e

    # ── Command Execution ────────────────────────────────────────────

    def _shell_args(self, command: Command) -> list[str]:
        return ["adb", "-s", self.serial, "shell", device_command(command)]

    def shell(self, command: Command) -> str:
        """Run ``adb -s <serial> shell <command>`` and return its stdout."""
        full = self._shell_args(command)
        try:
            result = subprocess.run(full, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            self.logger.error("ADB shell failed: %s\nStderr: %s", " ".join(full), e.stderr)
            raise

    def spawn_shell(self, command: Command) -> subprocess.Popen[bytes]:
        """Start ``adb shell <command>`` without waiting (e.g. ``screenrecord``, ``logcat``).

        The caller owns the process: stop it on the device (``pkill``) and ``wait()`` for it.
        """
        return subprocess.Popen(
            self._shell_args(command), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def stream_shell(self, command: Command) -> subprocess.Popen[str]:
        """Start ``adb shell <command>`` with its stdout readable line by line (e.g. ``logcat``).

        The caller owns the process: ``terminate()`` and ``wait()`` it when done.
        """
        return subprocess.Popen(
            self._shell_args(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    def exec_out(self, command: Command) -> bytes:
        """Run ``adb exec-out <command>`` and return the raw bytes (e.g. ``screencap -p``)."""
        full = ["adb", "-s", self.serial, "exec-out", device_command(command)]
        return subprocess.run(full, capture_output=True, check=True).stdout

    def cmd(self, command: Command) -> str:
        """Run ``adb -s <serial> <command>`` (host-side adb command, not ``shell``)."""
        args = shlex.split(command) if isinstance(command, str) else [str(a) for a in command]
        full = ["adb", "-s", self.serial, *args]
        return subprocess.run(full, capture_output=True, text=True, check=True).stdout

    async def async_shell(self, command: Command) -> str:
        """Run ``adb shell`` asynchronously."""
        full = self._shell_args(command)
        proc = await asyncio.create_subprocess_exec(
            *full,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode is not None and proc.returncode != 0:
            cmd_str = " ".join(full)
            self.logger.error(
                "ADB async shell failed: %s\nStderr: %s", cmd_str, stderr.decode().strip()
            )
            raise subprocess.CalledProcessError(
                proc.returncode, cmd_str, output=stdout, stderr=stderr
            )
        return stdout.decode().strip()

    # ── File Operations ──────────────────────────────────────────────

    def pull(self, remote_path: str, local_path: str | Path) -> str:
        """Copy *remote_path* to *local_path* (a directory or the target file path).

        Returns the local path of the pulled file.
        """
        local = Path(local_path)
        target = local / posixpath.basename(remote_path) if local.is_dir() else local
        self.logger.info("Pulling %s → %s", remote_path, target)
        self.cmd(["pull", remote_path, str(local)])
        return str(target)

    def push(self, local_path: str | Path, remote_path: str) -> str:
        self.logger.info("Pushing %s → %s", local_path, remote_path)
        return self.cmd(["push", str(local_path), remote_path])

    def rm(self, file_path: str) -> None:
        self.logger.info("Removing %s", file_path)
        self.shell(["rm", file_path])

    def mkdir(self, path: str) -> None:
        self.shell(["mkdir", "-p", path])

    # ── Device Lifecycle ─────────────────────────────────────────────

    def root(self) -> None:
        self.logger.info("Rooting device…")
        try:
            self.cmd("root")
        except subprocess.CalledProcessError:
            raise DeviceIsSecureError("Device is secure and cannot be rooted") from None

    def wait_for_device(self) -> None:
        self.logger.info("Waiting for device…")
        self.cmd("wait-for-device")


def wait_for_boot(adb: AdbClient, timeout: float = 180, interval: float = 2) -> None:
    """Block until ``sys.boot_completed`` is ``1`` on *adb*'s device.

    Raises:
        DeviceTimeoutError: When it does not happen within *timeout* seconds.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if adb.shell("getprop sys.boot_completed").strip() == "1":
                return
        except subprocess.CalledProcessError:
            pass  # adb is up but the shell is not ready yet
        time.sleep(interval)
    raise DeviceTimeoutError(f"Device {adb.serial} did not finish booting within {timeout}s")

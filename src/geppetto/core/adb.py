from __future__ import annotations

import asyncio
import logging
import shlex
import subprocess

from ..exceptions import DeviceIsSecureError


class AdbClient:
    """Low-level ADB transport layer.

    Provides synchronous and asynchronous methods for executing ADB commands
    on a specific device identified by its serial number.  All commands are
    executed **without** ``shell=True`` to prevent shell-injection.
    """

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.logger = logging.getLogger(f"geppetto.adb.{serial}")
        self.real_serial: str = self.shell("getprop ro.serialno").strip()

    # ── Command Execution ────────────────────────────────────────────

    def shell(self, command: str) -> str:
        """Run ``adb -s <serial> shell <command>``."""
        full = ["adb", "-s", self.serial, "shell", *shlex.split(command)]
        try:
            result = subprocess.run(full, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            self.logger.error("ADB shell failed: %s\nStderr: %s", " ".join(full), e.stderr)
            raise

    def cmd(self, command: str) -> str:
        """Run ``adb -s <serial> <command>`` (non-shell)."""
        full = ["adb", "-s", self.serial, *shlex.split(command)]
        return subprocess.run(full, capture_output=True, text=True, check=True).stdout

    async def async_shell(self, command: str) -> str:
        """Run ``adb shell`` asynchronously."""
        full = ["adb", "-s", self.serial, "shell", *shlex.split(command)]
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

    def pull(self, remote_path: str, local_path: str) -> str:
        file_name = remote_path.rsplit("/", 1)[-1]
        self.logger.info("Pulling %s → %s/%s", remote_path, local_path, file_name)
        self.cmd(f"pull {remote_path} {local_path}")
        return f"{local_path}/{file_name}"

    def push(self, local_path: str, remote_path: str) -> str:
        self.logger.info("Pushing %s → %s", local_path, remote_path)
        return self.cmd(f"push {local_path} {remote_path}")

    def rm(self, file_path: str) -> None:
        self.logger.info("Removing %s", file_path)
        self.shell(f"rm {file_path}")

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

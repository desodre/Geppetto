from __future__ import annotations

import shlex
import subprocess


class FastbootClient:
    """Low-level Fastboot transport layer."""

    def __init__(self, serial: str) -> None:
        self._serial = serial

    def cmd(self, command: str) -> str:
        """Run ``fastboot -s <serial> <command>``."""
        full = ["fastboot", "-s", self._serial, *shlex.split(command)]
        result = subprocess.run(full, capture_output=True, text=True, check=True)
        return result.stdout or result.stderr

    def flash(self, image_name: str, image_path: str) -> str:
        return self.cmd(f"flash {image_name} {image_path}")

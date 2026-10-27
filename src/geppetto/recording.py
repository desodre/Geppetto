"""Screen recording that runs while your code runs (``adb shell screenrecord`` in background)."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .core.adb import AdbClient

#: Android stops ``screenrecord`` by itself after this many seconds.
MAX_SECONDS = 180


class ScreenRecording:
    """A screen recording in progress on the device.

    ``start()`` launches ``screenrecord`` in the background; ``stop(save_to)`` ends it, pulls the
    MP4 and deletes it from the device; ``discard()`` ends it and only deletes it. Recordings are
    capped at :data:`MAX_SECONDS` by Android.
    """

    DEVICE_DIR = "/sdcard/DCIM/Geppetto"

    def __init__(self, adb: AdbClient, name: str, time_limit: int = MAX_SECONDS) -> None:
        self._adb = adb
        self.device_path = f"{self.DEVICE_DIR}/{name}.mp4"
        self.time_limit = min(time_limit, MAX_SECONDS)
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> ScreenRecording:
        self._adb.mkdir(self.DEVICE_DIR)
        self._process = self._adb.spawn_shell(
            ["screenrecord", "--time-limit", self.time_limit, self.device_path]
        )
        return self

    def _end(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            # SIGINT makes screenrecord finish the MP4 (killing adb would leave it broken).
            self._adb.shell("pkill -INT screenrecord")
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
        time.sleep(0.5)  # the file is closed right after the process exits

    def stop(self, save_to: str | Path) -> str:
        """End the recording and pull it to *save_to* (file or folder). Returns the local path."""
        self._end()
        local = self._adb.pull(self.device_path, save_to)
        self._adb.rm(self.device_path)
        return local

    def discard(self) -> None:
        """End the recording and delete it from the device."""
        self._end()
        try:
            self._adb.rm(self.device_path)
        except subprocess.CalledProcessError:
            pass  # nothing was written (recording never started)

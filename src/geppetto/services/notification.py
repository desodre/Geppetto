from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.adb import AdbClient


class NotificationService:
    """Controls the notification shade and quick settings panel."""

    def __init__(self, adb: AdbClient) -> None:
        self._adb = adb

    def open(self) -> None:
        self._adb.shell("cmd statusbar expand-notifications")
        self._adb.logger.info("Opening notifications")

    def open_quick_settings(self) -> None:
        self._adb.shell("cmd statusbar expand-settings")

    def collapse(self) -> None:
        self._adb.shell("cmd statusbar collapse")

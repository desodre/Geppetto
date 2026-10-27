from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.adb import AdbClient


class LockscreenService:
    """Controls the device lock screen via ``locksettings`` commands.

    The current credential is kept in memory (``clear``/``verify`` need ``--old``) but is
    never written to the logs.

    Based on https://developer.android.com/reference/android/app/KeyguardManager
    """

    def __init__(self, adb: AdbClient) -> None:
        self._adb = adb
        self.password: str | None = None

    def __repr__(self) -> str:
        return f"LockscreenService(credential={'set' if self.password else 'none'})"

    def _old(self) -> list[str]:
        return ["--old", self.password] if self.password is not None else []

    def get_disabled(self) -> str:
        return self._adb.shell("locksettings get-disabled")

    def set_disabled(self) -> str:
        return self._adb.shell("locksettings set-disabled true")

    def set_pin(self, pin: str) -> None:
        self._adb.shell(["locksettings", "set-pin", *self._old(), pin])
        self.password = pin
        self._adb.logger.info("Lock PIN set")

    def set_password(self, password: str) -> None:
        self._adb.shell(["locksettings", "set-password", *self._old(), password])
        self.password = password
        self._adb.logger.info("Lock password set")

    def clear(self) -> None:
        self._adb.shell(["locksettings", "clear", *self._old()])
        self._adb.logger.info(
            "Lock cleared %s", "with the old credential" if self.password else "without credential"
        )
        self.password = None

    def verify(self) -> str:
        return self._adb.shell(["locksettings", "verify", *self._old()])

    def remove_cache(self) -> str:
        return self._adb.shell("locksettings remove-cache")

    def set_resume_on_reboot_provider_package(self, package_name: str) -> str:
        return self._adb.shell(
            ["locksettings", "set-resume-on-reboot-provider-package", package_name]
        )

    def require_strong_auth(self, reason: str) -> str:
        return self._adb.shell(["locksettings", "require-strong-auth", reason])

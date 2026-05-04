from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.adb import AdbClient


class LockscreenService:
    """Controls the device lock screen via ``locksettings`` commands.

    Based on https://developer.android.com/reference/android/app/KeyguardManager
    """

    def __init__(self, adb: AdbClient) -> None:
        self._adb = adb
        self.password: str | None = None

    def get_disabled(self) -> str:
        return self._adb.shell("locksettings get-disabled")

    def set_disabled(self) -> str:
        return self._adb.shell("locksettings set-disabled true")

    def set_pin(self, pin: str) -> None:
        self.password = pin
        self._adb.shell(f"locksettings set-pin {pin}")
        self._adb.logger.info("Setting lock PIN: %s", pin)

    def set_password(self, password: str) -> None:
        self.password = password
        self._adb.shell(f"locksettings set-password {password}")
        self._adb.logger.info("Setting lock PASSWORD: %s", password)

    def clear(self) -> None:
        if self.password is not None:
            self._adb.shell(f"locksettings clear --old {self.password}")
            self._adb.logger.info("Clearing lock with old credential")
        else:
            self._adb.shell("locksettings clear")
            self._adb.logger.info("Clearing lock without credential")

    def verify(self) -> str:
        if self.password is not None:
            return self._adb.shell(f"locksettings verify --old {self.password}")
        return self._adb.shell("locksettings verify")

    def remove_cache(self) -> str:
        return self._adb.shell("locksettings remove-cache")

    def set_resume_on_reboot_provider_package(self, package_name: str) -> str:
        return self._adb.shell(f"locksettings set-resume-on-reboot-provider-package {package_name}")

    def require_strong_auth(self, reason: str) -> str:
        return self._adb.shell(f"locksettings require-strong-auth {reason}")

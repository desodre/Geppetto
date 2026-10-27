from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.wifi_security import WifiSecurityType

if TYPE_CHECKING:
    from ..core.adb import AdbClient


class WifiService:
    """Controls Wi-Fi connections via ``cmd wifi``."""

    def __init__(self, adb: AdbClient) -> None:
        self._adb = adb

    def connect(
        self,
        ssid: str,
        wifi_security_type: WifiSecurityType,
        password: str = "",
    ) -> str:
        """Connect to *ssid*. The password is never logged."""
        # `-x` takes the SSID hex-encoded (UTF-8), so any character in the name survives.
        hex_ssid = ssid.encode("utf-8").hex()

        args = ["cmd", "wifi", "connect-network", hex_ssid, wifi_security_type.value]
        if wifi_security_type not in (WifiSecurityType.OPEN, WifiSecurityType.OWE):
            args.append(password)  # quoted for the device shell: spaces and symbols are safe
        args.append("-x")

        self._adb.logger.info("Connecting to WiFi SSID: %s Type: %s", ssid, wifi_security_type.name)
        return self._adb.shell(args)

    def enable(self) -> None:
        self._adb.logger.info("Enabling WiFi")
        self._adb.shell("cmd wifi set-wifi-enabled enabled")

    def disable(self) -> None:
        self._adb.logger.info("Disabling WiFi")
        self._adb.shell("cmd wifi set-wifi-enabled disabled")

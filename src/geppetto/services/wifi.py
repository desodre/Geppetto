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
        # Hex-encode the SSID to prevent shell-escaping issues with special characters
        hex_ssid = "".join(f"{ord(c):02x}" for c in ssid)

        if wifi_security_type in (WifiSecurityType.OPEN, WifiSecurityType.OWE):
            cmd = f'cmd wifi connect-network "{hex_ssid}" {wifi_security_type.value} -x'
        else:
            cmd = f'cmd wifi connect-network "{hex_ssid}" {wifi_security_type.value} {password} -x'

        self._adb.logger.info("Connecting to WiFi SSID: %s Type: %s", ssid, wifi_security_type.name)
        return self._adb.shell(cmd)

    def enable(self) -> None:
        self._adb.logger.info("Enabling WiFi")
        self._adb.shell("cmd wifi set-wifi-enabled enabled")

    def disable(self) -> None:
        self._adb.logger.info("Disabling WiFi")
        self._adb.shell("cmd wifi set-wifi-enabled disabled")

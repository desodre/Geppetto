from __future__ import annotations

import time

from .._logging import DeviceLogger

try:
    import brainstem
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "Acroname dependencies are missing. Install them with: pip install geppetto[hardware]"
    ) from _exc


class AcronameController:
    """Controls an Acroname USBHub3p device (8 ports, 0-7)."""

    _PORT_RANGE = range(8)

    def __init__(self) -> None:
        self.stem = brainstem.stem.USBHub3p()
        self.stem.discoverAndConnect(1)
        self.logger = DeviceLogger.get_logger("USBHub3p", component="Acroname")

        if not self.stem.isConnected():
            raise ConnectionError("Acroname device not connected.")
        self.logger.info("Acroname device connected.")

    def _validate_port(self, port: int) -> None:
        if port not in self._PORT_RANGE:
            raise ValueError(f"Invalid port {port}. Must be 0-7.")

    def enable_port(self, port: int) -> None:
        self._validate_port(port)
        self.stem.usb.setPortEnable(port)
        self.logger.info("Enabled port %d", port)

    def disable_port(self, port: int) -> None:
        self._validate_port(port)
        self.stem.usb.setPortDisable(port)
        self.logger.info("Disabled port %d", port)

    def reset_and_close(self) -> None:
        sequence = [0, 2, 4, 6, 1, 3, 5, 7]
        for port in sequence:
            self.enable_port(port)
            time.sleep(0.25)
        for port in sequence:
            self.disable_port(port)
            time.sleep(0.25)

    def close(self) -> None:
        self.stem.disconnect()
        self.logger.info("Acroname device closed.")

    def __del__(self) -> None:
        self.close()

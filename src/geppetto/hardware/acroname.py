from __future__ import annotations

import time
from types import TracebackType

from .._logging import DeviceLogger

try:
    import brainstem
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "Acroname dependencies are missing. "
        "Install them with: pip install 'geppetto-android[hardware]'"
    ) from _exc


class AcronameController:
    """Controls an Acroname USBHub3p device (8 ports, 0-7).

    Use it as a context manager so the hub is always released::

        with AcronameController() as hub:
            hub.disable_port(3)
    """

    _PORT_RANGE = range(8)

    def __init__(self) -> None:
        self.logger = DeviceLogger.get_logger("USBHub3p", component="Acroname", result_dir=None)
        self._connected = False
        self.stem = brainstem.stem.USBHub3p()
        self.stem.discoverAndConnect(1)

        if not self.stem.isConnected():
            raise ConnectionError("Acroname device not connected.")
        self._connected = True
        self.logger.info("Acroname device connected.")

    def __enter__(self) -> AcronameController:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

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
        """Power-cycle every port, then release the hub."""
        sequence = [0, 2, 4, 6, 1, 3, 5, 7]
        for port in sequence:
            self.enable_port(port)
            time.sleep(0.25)
        for port in sequence:
            self.disable_port(port)
            time.sleep(0.25)
        self.close()

    def close(self) -> None:
        """Release the hub. Safe to call more than once."""
        if not self._connected:
            return
        self.stem.disconnect()
        self._connected = False
        self.logger.info("Acroname device closed.")

    def __del__(self) -> None:
        # Last resort only: prefer `with` / close(). Never raise during garbage collection.
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

"""Geppetto — Android UI Automation Framework.

Just as Geppetto brought Pinocchio to life, this tool brings your
Android tests to life through automation.
"""

__version__ = "2.0.4"

from typing import Any

from ._logging import DeviceLogger
from .device import Device
from .exceptions import DeviceIsSecureError, DeviceTimeoutError, WidgetNotFoundError
from .models.by import By
from .models.common_classes import CommonClasses
from .models.direction import Direction
from .models.wifi_security import WifiSecurityType
from .ui.bounds import Bounds
from .ui.children import Children
from .ui.widget import Widget
from .ui.window_dump import WindowDump


# Lazy imports for optional dependencies
def __getattr__(name: str) -> Any:
    if name == "ScreenAnalyzer":
        from .analyzers.screen import ScreenAnalyzer

        return ScreenAnalyzer
    if name == "Colors":
        from .analyzers.screen import Colors

        return Colors
    if name == "VideoAnalyzer":
        from .analyzers.video import VideoAnalyzer

        return VideoAnalyzer
    if name == "AcronameController":
        from .hardware.acroname import AcronameController

        return AcronameController

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Core
    "Device",
    # UI
    "Bounds",
    "Children",
    "Widget",
    "WindowDump",
    # Models
    "By",
    "Direction",
    "WifiSecurityType",
    "CommonClasses",
    # Exceptions
    "DeviceIsSecureError",
    "DeviceTimeoutError",
    "WidgetNotFoundError",
    # Logging
    "DeviceLogger",
    # Optional (lazy)
    "ScreenAnalyzer",
    "Colors",
    "VideoAnalyzer",
    "AcronameController",
]

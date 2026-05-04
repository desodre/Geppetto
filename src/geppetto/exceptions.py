class WidgetNotFoundError(Exception):
    """Raised when a widget is not found in the window dump."""


class DeviceTimeoutError(Exception):
    """Raised when a timeout expires while waiting for a widget or activity."""


class DeviceIsSecureError(Exception):
    """Raised when a device is running a secure build and cannot be rooted."""

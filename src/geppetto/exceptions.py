class GeppettoError(Exception):
    """Base class for every error raised by Geppetto."""


class WidgetNotFoundError(GeppettoError):
    """Raised when a widget is not found in the window dump."""


class DeviceTimeoutError(GeppettoError):
    """Raised when a timeout expires while waiting for a widget, activity or boot."""


class DeviceIsSecureError(GeppettoError):
    """Raised when a device is running a secure build and cannot be rooted."""


class DeviceNotFoundError(GeppettoError):
    """Raised when the device does not answer adb (offline, unauthorized or wrong serial)."""


class EmulatorError(GeppettoError):
    """Raised when the Android emulator is missing, the AVD does not exist or it fails to start."""


class AdbCommandError(GeppettoError):
    """A host-side ``adb`` command failed; the message carries what adb printed."""

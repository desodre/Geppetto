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


class LogNotFoundError(GeppettoError):
    """An expected logcat line did not show up (or a forbidden one did)."""


class AppCrashedError(GeppettoError):
    """The app crashed (Java exception, ANR or native signal) while it was being watched."""


class CarloError(GeppettoError):
    """The Carlo agent could not be started, or broke or refused its protocol.

    Attributes:
        code: Stable machine-readable reason (a protocol code such as ``"bad_magic"`` or
            ``"unavailable"``, or a host-side one such as ``"timeout"``), ``None`` if unknown.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code

"""UI backends: where :class:`~geppetto.Device` reads the hierarchy and screen size from.

``uiautomator2`` (default) talks to the uiautomator2 agent; ``carlo`` talks to a Carlo agent
session (:mod:`geppetto.core.carlo`). Taps, text and keys always go through ``adb shell``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Protocol, cast

from ..exceptions import CarloError
from .adb import AdbClient
from .carlo import CarloSession, parse_wm_size

#: Names accepted by :func:`create_backend` (and ``Device(backend=...)``).
BACKEND_NAMES = ("uiautomator2", "carlo")
_WM_SIZE_TIMEOUT = 30.0


class UiBackend(Protocol):
    """What :class:`~geppetto.Device` needs from a UI backend."""

    def dump_hierarchy(self) -> str:
        """The current UI hierarchy as uiautomator-style XML."""
        ...

    def window_size(self) -> tuple[int, int]:
        """Screen ``(width, height)`` in pixels."""
        ...

    def close(self) -> None:
        """Release the backend's resources. Idempotent."""
        ...


class Uiautomator2Backend:
    """Backend over ``uiautomator2.Device`` (installs its agent on first use).

    Args:
        serial: Device serial; ignored when *u2* is given.
        u2: An existing ``uiautomator2.Device`` (or a stand-in in tests).
    """

    def __init__(self, serial: str | None = None, *, u2: object | None = None) -> None:
        if u2 is None:
            from uiautomator2 import Device as U2Device  # heavy: only when this backend is used

            u2 = U2Device(serial=serial)
        self.u2: Any = u2

    def dump_hierarchy(self) -> str:
        """Dump the UI hierarchy through uiautomator2.

        Returns:
            The hierarchy XML.
        """
        return str(self.u2.dump_hierarchy())

    def window_size(self) -> tuple[int, int]:
        """Screen size as uiautomator2 reports it.

        Returns:
            ``(width, height)`` in the current orientation.
        """
        return cast(tuple[int, int], tuple(self.u2.window_size()))

    def wait_widget(self, attribute: str, value: str, timeout: float) -> bool:
        """Wait with uiautomator2's own selector (``text``, ``resourceId``…).

        Returns:
            ``True`` if the widget appeared within *timeout* seconds.
        """
        return bool(self.u2(**{attribute: value}).wait(timeout=timeout))

    def close(self) -> None:
        """Nothing to release: the uiautomator2 agent stays installed for the next run."""


class CarloBackend:
    """Backend over a Carlo agent session; the screen size comes from ``wm size``.

    Args:
        adb: Transport of the device.
        binary: Local Carlo binary; defaults to ``$GEPPETTO_CARLO_BINARY``.
        sha256: Expected SHA-256 of *binary*.
        hierarchy_timeout: Seconds allowed for each hierarchy dump.

    Raises:
        CarloError: When the session cannot be started (see :meth:`CarloSession.start`).
    """

    def __init__(
        self,
        adb: AdbClient,
        binary: str | Path | None = None,
        *,
        sha256: str | None = None,
        hierarchy_timeout: float = 30.0,
    ) -> None:
        self._adb = adb
        self.session = CarloSession(
            adb, binary, sha256=sha256, hierarchy_timeout=hierarchy_timeout
        ).start()

    def dump_hierarchy(self) -> str:
        """Ask Carlo for the UI hierarchy (``hierarchy.dump``).

        Returns:
            The hierarchy XML sent by Carlo.

        Raises:
            CarloError: Carlo refused (e.g. ``unavailable``) or the connection failed.
        """
        return self.session.client.hierarchy_dump()

    def window_size(self) -> tuple[int, int]:
        """Screen size from ``adb shell wm size``.

        Returns:
            ``(width, height)`` from ``wm size`` (override size first, natural orientation).

        Raises:
            CarloError: ``invalid_wm_size`` when the output cannot be parsed, ``timeout``
                when ``wm size`` does not answer within 30 s, or ``adb`` when it fails.
        """
        try:
            output = self._adb.shell("wm size", timeout=_WM_SIZE_TIMEOUT)
        except subprocess.TimeoutExpired as e:
            raise CarloError("adb shell wm size timed out", code="timeout") from e
        except (subprocess.CalledProcessError, OSError) as e:
            raise CarloError("adb shell wm size failed", code="adb") from e
        return parse_wm_size(output)

    def close(self) -> None:
        """End the Carlo session and remove everything it left on the device."""
        self.session.close()


def create_backend(
    backend: str | UiBackend,
    adb: AdbClient,
    *,
    carlo_binary: str | Path | None = None,
) -> UiBackend:
    """Build the UI backend named *backend* (an instance is returned as is).

    Returns:
        A ready backend.

    Raises:
        ValueError: Unknown backend name.
        CarloError: The Carlo session could not be started.
    """
    if not isinstance(backend, str):
        return backend
    if backend == "uiautomator2":
        return Uiautomator2Backend(adb.serial)
    if backend == "carlo":
        return CarloBackend(adb, carlo_binary)
    names = ", ".join(BACKEND_NAMES)
    raise ValueError(f"Unknown UI backend {backend!r}; expected one of {names}")

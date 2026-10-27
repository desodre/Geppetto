"""pytest plugin: Geppetto devices as fixtures.

Registered through the ``pytest11`` entry point, so installing ``geppetto-android`` is enough::

    def test_login(device):
        device.open_app("com.example")
        ...

Run with ``pytest --serial <serial>`` (repeatable), ``--all-devices``, or with a single device
connected (picked automatically). Without a device the tests that need one are skipped.

Options (also settable in ``[tool.pytest.ini_options]`` through the ini names):

``--serial``               device serial; repeat for several (env ``GEPPETTO_SERIAL``, comma list)
``--all-devices``          every device ``adb devices`` reports as ready
``--geppetto-output``      result folder (default ``./results``)

Fixtures:

``device``                 the first selected :class:`~geppetto.Device` (session scope)
``devices``                every selected device, in order (session scope)
``geppetto_serials``       the selected serials
``geppetto_device_factory`` builds a ``Device`` from a serial; override it to customise creation
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from .core.adb import list_devices

if TYPE_CHECKING:  # Device pulls uiautomator2: imported only when a test asks for a device
    from .device import Device

DeviceFactory = Callable[[str], "Device"]


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("geppetto", "Geppetto (Android devices)")
    group.addoption(
        "--serial",
        action="append",
        default=[],
        dest="geppetto_serial",
        metavar="SERIAL",
        help="Device serial to run on (repeat for several). Env: GEPPETTO_SERIAL (comma list).",
    )
    group.addoption(
        "--all-devices",
        action="store_true",
        default=False,
        dest="geppetto_all_devices",
        help="Run on every device `adb devices` reports as ready.",
    )
    group.addoption(
        "--geppetto-output",
        default=None,
        dest="geppetto_output",
        metavar="DIR",
        help="Folder for logs and artifacts (default: ini geppetto_output or ./results).",
    )
    parser.addini("geppetto_output", "Folder for logs and artifacts.", default="./results")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "geppetto: test uses a Geppetto device (set automatically by the fixtures)."
    )


def _output_dir(config: pytest.Config) -> Path:
    option = config.getoption("geppetto_output")
    return Path(option or config.getini("geppetto_output"))


def _selected_serials(config: pytest.Config) -> list[str]:
    serials: list[str] = list(config.getoption("geppetto_serial"))
    if not serials and os.environ.get("GEPPETTO_SERIAL"):
        serials = [s.strip() for s in os.environ["GEPPETTO_SERIAL"].split(",") if s.strip()]
    if config.getoption("geppetto_all_devices"):
        serials += [s for s in list_devices() if s not in serials]
    if not serials:
        connected = list_devices()
        if len(connected) == 1:  # one device plugged in: no need to name it
            serials = connected
    return list(dict.fromkeys(serials))


@pytest.fixture(scope="session")
def geppetto_serials(pytestconfig: pytest.Config) -> list[str]:
    """Serials chosen by ``--serial``/``GEPPETTO_SERIAL``/``--all-devices`` (or the only device)."""
    return _selected_serials(pytestconfig)


@pytest.fixture(scope="session")
def geppetto_device_factory(pytestconfig: pytest.Config) -> DeviceFactory:
    """How a serial becomes a :class:`Device`. Override in ``conftest.py`` to customise."""
    output = _output_dir(pytestconfig)

    def factory(serial: str) -> Device:
        from .device import Device

        return Device(serial, output_dir=output)

    return factory


@pytest.fixture(scope="session")
def devices(geppetto_serials: list[str], geppetto_device_factory: DeviceFactory) -> list[Device]:
    """Every selected device, created once per session."""
    if not geppetto_serials:
        pytest.skip(
            "no Android device selected: connect one or pass --serial / --all-devices "
            "(GEPPETTO_SERIAL also works)"
        )
    return [geppetto_device_factory(serial) for serial in geppetto_serials]


@pytest.fixture(scope="session")
def device(devices: list[Device]) -> Iterator[Device]:
    """The first selected device (session scope)."""
    yield devices[0]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if {"device", "devices"} & set(getattr(item, "fixturenames", ())):
            item.add_marker("geppetto")

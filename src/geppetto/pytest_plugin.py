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
``--geppetto-artifacts``   ``on-failure`` (default), ``always`` or ``never``
``--geppetto-record``      record the screen during each device test (kept with the artifacts)

Artifacts of a device test go to ``<device result folder>/Tests/<test id>/``: ``screenshot.png``,
``window_dump.xml``, ``logcat.txt`` (only what the test produced: the buffer is cleared before it)
and ``screenrecord.mp4`` with ``--geppetto-record``. One failing artifact never hides the others:
its error goes to ``<name>.error.txt``.

Reports: the folder is printed in the failure section, recorded as a JUnit ``<property>``
(``geppetto_artifacts[<serial>]``) and, with pytest-html, the screenshot is embedded in the report
and the other files are linked.

Fixtures:

``device``                 the first selected :class:`~geppetto.Device` (session scope)
``devices``                every selected device, in order (session scope)
``geppetto_serials``       the selected serials
``geppetto_device_factory`` builds a ``Device`` from a serial; override it to customise creation
"""

from __future__ import annotations

import base64
import logging
import os
import re
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from .core.adb import list_devices

if TYPE_CHECKING:  # Device pulls uiautomator2: imported only when a test asks for a device
    from .device import Device
    from .recording import ScreenRecording

logger = logging.getLogger("geppetto.pytest")

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
    group.addoption(
        "--geppetto-artifacts",
        choices=("on-failure", "always", "never"),
        default=None,
        dest="geppetto_artifacts",
        help="When to save screenshot/window dump/logcat/video of device tests "
        "(default: ini geppetto_artifacts or on-failure).",
    )
    group.addoption(
        "--geppetto-record",
        action="store_true",
        default=False,
        dest="geppetto_record",
        help="Record the screen during each device test (max 180 s per test, Android limit).",
    )
    parser.addini("geppetto_output", "Folder for logs and artifacts.", default="./results")
    parser.addini("geppetto_artifacts", "on-failure | always | never", default="on-failure")


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


# ── Artifacts ────────────────────────────────────────────────────────


@dataclass
class _Capture:
    """What the plugin tracks for one test on one device."""

    device: Device
    recording: ScreenRecording | None = None
    folder: Path | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)


_CAPTURES = pytest.StashKey[list[_Capture]]()


def _artifacts_mode(config: pytest.Config) -> str:
    return str(config.getoption("geppetto_artifacts") or config.getini("geppetto_artifacts"))


def _uses_device(item: pytest.Item) -> bool:
    return bool({"device", "devices"} & set(getattr(item, "fixturenames", ())))


def _safe_name(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nodeid).strip("_")[:150] or "test"


def _save(capture: _Capture, name: str, write: Callable[[Path], object]) -> None:
    """Write one artifact; a failure becomes ``<name>.error.txt`` and never stops the others."""
    assert capture.folder is not None
    path = capture.folder / name
    try:
        write(path)
        capture.artifacts[name] = path
    except Exception as erro:  # noqa: BLE001 — the test result matters more than one artifact
        (capture.folder / f"{name}.error.txt").write_text(f"{type(erro).__name__}: {erro}\n")
        logger.warning("Could not save %s for %s: %s", name, capture.device.serial, erro)


def _collect_one(item: pytest.Item, capture: _Capture) -> None:
    dev = capture.device
    capture.folder = Path(dev.result_path) / "Tests" / _safe_name(item.nodeid)
    capture.folder.mkdir(parents=True, exist_ok=True)
    _save(capture, "screenshot.png", lambda p: p.write_bytes(dev.adb.exec_out("screencap -p")))
    _save(capture, "window_dump.xml", lambda p: p.write_text(str(dev.get_window_dump())))
    _save(capture, "logcat.txt", lambda p: p.write_text(dev.dump_logcat()))
    recording = capture.recording
    if recording is not None:
        capture.recording = None
        _save(capture, "screenrecord.mp4", lambda p: recording.stop(p))


def _collect(item: pytest.Item) -> None:
    for capture in item.stash.get(_CAPTURES, []):
        if capture.folder is None:  # setup failed, then call: collect once
            _collect_one(item, capture)


@pytest.fixture(autouse=True)
def _geppetto_capture(request: pytest.FixtureRequest) -> Generator[None]:
    """Before a device test: clear logcat, start recording; after: drop what is not needed."""
    item = request.node
    if not _uses_device(item) or _artifacts_mode(request.config) == "never":
        yield
        return
    # The devices this test really uses (a conftest may override `device` alone).
    used = (
        request.getfixturevalue("devices")
        if "devices" in item.fixturenames
        else [request.getfixturevalue("device")]
    )
    captures = []
    for dev in used:
        try:
            dev.clear_logcat()
        except Exception as erro:  # noqa: BLE001
            logger.warning("Could not clear logcat on %s: %s", dev.serial, erro)
        recording = None
        if request.config.getoption("geppetto_record"):
            try:
                recording = dev.start_recording(_safe_name(item.name))
            except Exception as erro:  # noqa: BLE001
                logger.warning("Could not start recording on %s: %s", dev.serial, erro)
        captures.append(_Capture(dev, recording))
    item.stash[_CAPTURES] = captures
    yield
    for capture in captures:
        if capture.recording is not None:  # test passed and artifacts were not kept
            capture.recording.discard()
            capture.recording = None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if _CAPTURES not in item.stash or report.when == "teardown":
        return report
    mode = _artifacts_mode(item.config)
    if report.failed or (mode == "always" and report.when == "call"):
        _collect(item)
        for capture in item.stash[_CAPTURES]:
            if capture.folder is not None:
                _attach(item, report, capture)
    return report


def _attach(item: pytest.Item, report: pytest.TestReport, capture: _Capture) -> None:
    """Point the reports at the artifacts: terminal section, JUnit property, pytest-html."""
    assert capture.folder is not None
    serial = capture.device.serial
    report.sections.append((f"geppetto artifacts ({serial})", str(capture.folder)))
    # JUnit writes the properties of the teardown report, which copies item.user_properties.
    propriedade = (f"geppetto_artifacts[{serial}]", str(capture.folder))
    if propriedade not in item.user_properties:
        item.user_properties.append(propriedade)

    html = item.config.pluginmanager.getplugin("html")
    if html is None:
        return
    extras = list(getattr(report, "extras", []))
    screenshot = capture.artifacts.get("screenshot.png")
    if screenshot is not None:
        extras.append(
            html.extras.png(
                base64.b64encode(screenshot.read_bytes()).decode(), name=f"{serial} screenshot"
            )
        )
    for name, path in capture.artifacts.items():
        if name != "screenshot.png":
            extras.append(html.extras.url(path.resolve().as_uri(), name=f"{serial} {name}"))
    report.extras = extras  # type: ignore[attr-defined]  # attribute pytest-html reads


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if {"device", "devices"} & set(getattr(item, "fixturenames", ())):
            item.add_marker("geppetto")

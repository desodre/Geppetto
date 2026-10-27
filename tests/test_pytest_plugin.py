"""The pytest plugin, exercised through pytester (an inner pytest run in this process)."""

from __future__ import annotations

import pytest

from geppetto.core import adb as adb_module

pytest_plugins = ["pytester"]

#: conftest for the inner runs: a Device built without hardware.
CONFTEST = """
import logging
import pytest
from geppetto import Device


CALLS = []


class FakeProcess:
    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


class FakeAdb:
    serial = "FAKE"

    def shell(self, command):
        CALLS.append(command)
        if command[:2] == ["logcat", "-d"]:
            return "10-27 12:00:00 E App: something broke\\n"
        return ""

    def exec_out(self, command):
        return b"PNG-BYTES"

    def mkdir(self, path):
        pass

    def spawn_shell(self, command):
        CALLS.append(command)
        return FakeProcess()

    def pull(self, remote, local):
        open(local, "wb").write(b"MP4")
        return str(local)

    def rm(self, path):
        CALLS.append(["rm", path])


class FakeU2:
    def dump_hierarchy(self):
        return "<hierarchy><node text='Login' bounds='[0,0][1,1]'/></hierarchy>"


@pytest.fixture(scope="session")
def geppetto_device_factory(tmp_path_factory):
    def factory(serial):
        dev = object.__new__(Device)
        dev._serial = serial
        dev.adb = FakeAdb()
        dev._u2 = FakeU2()
        dev.result_path = tmp_path_factory.mktemp(serial)
        dev.logger = logging.getLogger("geppetto.test")
        return dev
    return factory
"""


@pytest.fixture
def sem_aparelhos(monkeypatch):
    monkeypatch.setattr(adb_module, "list_devices", lambda: [])
    monkeypatch.setattr("geppetto.pytest_plugin.list_devices", lambda: [])
    monkeypatch.delenv("GEPPETTO_SERIAL", raising=False)


def test_options_are_registered(pytester):
    result = pytester.runpytest("--help")
    result.stdout.fnmatch_lines(["*--serial=SERIAL*", "*--all-devices*", "*--geppetto-output=DIR*"])


def test_device_fixture_uses_the_serial(pytester, sem_aparelhos):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        def test_um(device, devices):
            assert device.serial == "AAA"
            assert [d.serial for d in devices] == ["AAA", "BBB"]
        """
    )
    pytester.runpytest("--serial", "AAA", "--serial", "BBB").assert_outcomes(passed=1)


def test_serial_from_environment(pytester, sem_aparelhos, monkeypatch):
    monkeypatch.setenv("GEPPETTO_SERIAL", "ENV1, ENV2")
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        "def test_um(devices): assert [d.serial for d in devices] == ['ENV1', 'ENV2']"
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_single_connected_device_is_picked(pytester, sem_aparelhos, monkeypatch):
    monkeypatch.setattr("geppetto.pytest_plugin.list_devices", lambda: ["ONLY"])
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile("def test_um(device): assert device.serial == 'ONLY'")
    pytester.runpytest().assert_outcomes(passed=1)


def test_all_devices_adds_every_ready_device(pytester, sem_aparelhos, monkeypatch):
    monkeypatch.setattr("geppetto.pytest_plugin.list_devices", lambda: ["X1", "X2"])
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        "def test_um(devices): assert [d.serial for d in devices] == ['X0', 'X1', 'X2']"
    )
    pytester.runpytest("--serial", "X0", "--all-devices").assert_outcomes(passed=1)


def test_without_device_tests_are_skipped_with_a_reason(pytester, sem_aparelhos):
    pytester.makepyfile(
        """
        def test_precisa(device):
            pass

        def test_nao_precisa():
            pass
        """
    )
    result = pytester.runpytest("-rs")
    result.assert_outcomes(passed=1, skipped=1)
    result.stdout.fnmatch_lines(["*no Android device selected*"])


def test_tests_with_a_device_get_the_geppetto_marker(pytester, sem_aparelhos):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        def test_com(device):
            pass

        def test_sem():
            pass
        """
    )
    result = pytester.runpytest("--serial", "S", "-m", "geppetto", "-v")
    result.assert_outcomes(passed=1, deselected=1)


def test_list_devices_keeps_only_ready_ones(monkeypatch):
    import subprocess

    saida = (
        "List of devices attached\nAAA\tdevice\nBBB\tunauthorized\nCCC\toffline\nDDD\tdevice\n\n"
    )
    monkeypatch.setattr(
        adb_module.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=saida, stderr=""),
    )
    assert adb_module.list_devices() == ["AAA", "DDD"]


def _pasta(result, nome):
    """The artifacts folder the plugin printed for test *nome*."""
    import pathlib

    for line in result.stdout.lines:
        if "/Tests/" in line and nome in line:
            return pathlib.Path(line.strip().split()[-1])
    raise AssertionError("no artifacts section in the output:\n" + result.stdout.str())


def test_failure_saves_screenshot_dump_and_logcat(pytester, sem_aparelhos):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        def test_falha(device):
            assert False, "boom"

        def test_passa(device):
            pass
        """
    )
    result = pytester.runpytest("--serial", "S1")
    result.assert_outcomes(passed=1, failed=1)
    pasta = _pasta(result, "test_falha")
    assert (pasta / "screenshot.png").read_bytes() == b"PNG-BYTES"
    assert "Login" in (pasta / "window_dump.xml").read_text()
    assert "something broke" in (pasta / "logcat.txt").read_text()
    assert not (
        pasta.parent / "test_failure_saves_screenshot_dump_and_logcat.py_test_passa"
    ).exists()


def test_logcat_is_cleared_before_each_device_test(pytester, sem_aparelhos):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        from conftest import CALLS

        def test_um(device):
            assert "logcat -c" in CALLS
        """
    )
    pytester.runpytest("--serial", "S1").assert_outcomes(passed=1)


def test_record_keeps_the_video_only_on_failure(pytester, sem_aparelhos):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        from conftest import CALLS

        def test_passa(device):
            pass

        def test_falha(device):
            assert False

        def test_confere():
            removidos = [c for c in CALLS if c[0] == "rm"]
            assert len(removidos) == 2  # the passing video was discarded, the failing one pulled
        """
    )
    result = pytester.runpytest("--serial", "S1", "--geppetto-record")
    result.assert_outcomes(passed=2, failed=1)
    assert (_pasta(result, "test_falha") / "screenrecord.mp4").read_bytes() == b"MP4"


def test_always_and_never_modes(pytester, sem_aparelhos):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile("def test_passa(device): pass")
    always = pytester.runpytest("--serial", "S1", "--geppetto-artifacts=always", "-rA")
    assert (_pasta(always, "test_passa") / "screenshot.png").exists()

    pytester.makepyfile("def test_falha(device): assert False")
    never = pytester.runpytest("--serial", "S1", "--geppetto-artifacts=never")
    never.assert_outcomes(failed=1)
    assert "geppetto artifacts" not in never.stdout.str()


def test_broken_artifact_does_not_hide_the_others(pytester, sem_aparelhos):
    pytester.makeconftest(
        CONFTEST
        + """
def _quebra(self):
    raise RuntimeError("u2 agent gone")

FakeU2.dump_hierarchy = _quebra
"""
    )
    pytester.makepyfile("def test_falha(device): assert False")
    result = pytester.runpytest("--serial", "S1")
    pasta = _pasta(result, "test_falha")
    assert (pasta / "screenshot.png").exists() and (pasta / "logcat.txt").exists()
    assert "u2 agent gone" in (pasta / "window_dump.xml.error.txt").read_text()


def test_junit_gets_the_artifacts_folder(pytester, sem_aparelhos):
    import xml.etree.ElementTree as ET

    pytester.makeconftest(CONFTEST)
    pytester.makepyfile("def test_falha(device): assert False")
    pytester.runpytest("--serial", "S1", "--junitxml=junit.xml")
    props = {
        p.get("name"): p.get("value")
        for p in ET.parse(pytester.path / "junit.xml").iter("property")
    }
    assert props["geppetto_artifacts[S1]"].endswith("test_falha")


def test_pytest_html_embeds_the_screenshot_and_links_the_rest(pytester, sem_aparelhos):
    pytest.importorskip("pytest_html")
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile("def test_falha(device): assert False")
    pytester.runpytest("--serial", "S1", "--html=report.html", "--self-contained-html")
    html = (pytester.path / "report.html").read_text()
    assert "UE5HLUJZVEVT" in html  # base64 of b"PNG-BYTES": the screenshot is inside the report
    assert "S1 logcat.txt" in html and "S1 window_dump.xml" in html

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


class FakeAdb:
    serial = "FAKE"

    def shell(self, command):
        return ""


@pytest.fixture(scope="session")
def geppetto_device_factory(tmp_path_factory):
    def factory(serial):
        dev = object.__new__(Device)
        dev._serial = serial
        dev.adb = FakeAdb()
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

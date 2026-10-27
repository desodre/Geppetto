import subprocess

import pytest

from geppetto import DeviceNotFoundError
from geppetto.core import adb as adb_module
from geppetto.core.adb import AdbClient, device_command


def test_sequence_is_quoted_for_the_device_shell():
    assert (
        device_command(["am", "force-stop", "com.app; reboot"]) == "am force-stop 'com.app; reboot'"
    )
    assert device_command(["input", "text", "it's"]) == "input text 'it'\"'\"'s'"


def test_string_is_a_trusted_command_line():
    assert device_command("getprop ro.serialno") == "getprop ro.serialno"


def test_shell_sends_one_argument_after_shell(adb, adb_run):
    adb.shell(["echo", "a b"])
    assert adb_run.calls[-1] == ["adb", "-s", "SERIAL123", "shell", "echo 'a b'"]


def test_unreachable_device_raises_device_not_found(monkeypatch):
    def falha(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr="error: device 'X' not found")

    monkeypatch.setattr(adb_module.subprocess, "run", falha)
    with pytest.raises(DeviceNotFoundError, match="not found"):
        AdbClient("X")


def test_missing_adb_binary_raises_device_not_found(monkeypatch):
    def sem_adb(argv, **kwargs):
        raise FileNotFoundError("adb")

    monkeypatch.setattr(adb_module.subprocess, "run", sem_adb)
    with pytest.raises(DeviceNotFoundError):
        AdbClient("X")


def test_pull_returns_the_real_local_path(adb, adb_run, tmp_path):
    assert adb.pull("/sdcard/a.mp4", tmp_path) == str(tmp_path / "a.mp4")
    target = tmp_path / "renamed.mp4"
    assert adb.pull("/sdcard/a.mp4", target) == str(target)
    assert adb_run.calls[-1] == ["adb", "-s", "SERIAL123", "pull", "/sdcard/a.mp4", str(target)]

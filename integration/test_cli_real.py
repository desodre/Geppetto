"""The `geppetto` command line against a real device."""

import json

from .conftest import geppetto


def test_devices_lists_the_serial_as_ready(serial):
    result = geppetto("devices", "--json")
    assert result.returncode == 0, result.stderr
    assert {"serial": serial, "ready": True}.items() <= next(
        d for d in json.loads(result.stdout) if d["serial"] == serial
    ).items()


def test_doctor_has_no_failures_for_the_device(serial):
    result = geppetto("doctor", "-s", serial)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"✔ device {serial}" in result.stdout


def test_shot_saves_a_png(serial, tmp_path):
    destino = tmp_path / "tela.png"
    result = geppetto("shot", "-s", serial, "-o", str(destino))
    assert result.returncode == 0, result.stderr
    assert destino.read_bytes()[:4] == b"\x89PNG"


def test_record_saves_an_mp4(serial, tmp_path):
    destino = tmp_path / "video.mp4"
    result = geppetto("record", "-s", serial, "-t", "4", "-o", str(destino), timeout=60)
    assert result.returncode == 0, result.stderr
    assert b"ftyp" in destino.read_bytes()[:16]  # MP4 header: the recording was finalised


def test_unknown_serial_fails_in_one_line():
    result = geppetto("shot", "-s", "no-such-device")
    assert result.returncode == 1
    assert result.stderr.startswith("geppetto: ") and "Traceback" not in result.stderr

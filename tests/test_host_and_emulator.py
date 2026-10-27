import subprocess
from pathlib import Path

import pytest

from geppetto import DeviceNotFoundError, DeviceTimeoutError
from geppetto.core import emulator, host
from geppetto.exceptions import EmulatorError

DEVICES_L = """List of devices attached
RXCY103LPWT            device usb:1-3 product:a16xub model:SM_A166M device:a16x transport_id:1
emulator-5554          device product:sdk_gphone64 model:sdk_gphone64_x86_64 transport_id:4
192.168.0.10:41235     offline transport_id:5
adb-R58N-AbCd._adb-tls-connect._tcp unauthorized transport_id:6
"""


def test_parse_devices():
    entries = host.parse_devices(DEVICES_L)
    assert [(e.serial, e.state) for e in entries] == [
        ("RXCY103LPWT", "device"),
        ("emulator-5554", "device"),
        ("192.168.0.10:41235", "offline"),
        ("adb-R58N-AbCd._adb-tls-connect._tcp", "unauthorized"),
    ]
    usb, emu, wifi, mdns = entries
    assert usb.model == "SM_A166M" and usb.ready and not usb.is_emulator and not usb.is_wireless
    assert emu.is_emulator and wifi.is_wireless and mdns.is_wireless and not wifi.ready


def test_parse_mdns():
    saida = (
        "List of discovered mdns services\n"
        "adb-R58N-AbCd\t_adb-tls-connect._tcp.\t192.168.0.10:37000\n"
        "geppetto-a1b2c3\t_adb-tls-pairing._tcp.\t192.168.0.10:40111\n"
    )
    servicos = host.parse_mdns(saida)
    assert [(s.name, s.is_pairing, s.address) for s in servicos] == [
        ("adb-R58N-AbCd", False, "192.168.0.10:37000"),
        ("geppetto-a1b2c3", True, "192.168.0.10:40111"),
    ]


def fake_adb(monkeypatch, saidas):
    """`subprocess.run` that answers adb by the first matching argument prefix."""
    chamadas = []

    def run(argv, **kwargs):
        chamadas.append(argv)
        for prefixo, saida in saidas.items():
            if " ".join(argv).startswith(prefixo):
                return subprocess.CompletedProcess(argv, 0, stdout=saida, stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(host.subprocess, "run", run)
    return chamadas


def test_pair_and_connect_check_the_answer(monkeypatch):
    fake_adb(
        monkeypatch,
        {
            "adb pair": "Successfully paired to 192.168.0.10:40111 [guid=x]",
            "adb connect": "failed to connect to 192.168.0.10:5555",
        },
    )
    assert "Successfully" in host.pair("192.168.0.10:40111", "123456")
    with pytest.raises(DeviceNotFoundError, match="connect failed"):
        host.connect("192.168.0.10:5555")


def test_missing_adb(monkeypatch):
    def sem_adb(argv, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(host.subprocess, "run", sem_adb)
    with pytest.raises(DeviceNotFoundError, match="not installed"):
        host.devices()


def test_sdk_root_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ANDROID_SDK_ROOT", str(tmp_path))
    assert emulator.sdk_root() == tmp_path


def test_emulator_binary_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(emulator.shutil, "which", lambda name: None)
    monkeypatch.setattr(emulator, "sdk_root", lambda: tmp_path)
    with pytest.raises(EmulatorError, match="not found"):
        emulator.emulator_binary()


@pytest.fixture
def emu(monkeypatch, tmp_path):
    binario = tmp_path / "emulator"
    binario.write_text("")
    monkeypatch.setattr(emulator, "emulator_binary", lambda: binario)
    monkeypatch.setattr(
        emulator.subprocess,
        "run",
        lambda argv, **k: subprocess.CompletedProcess(
            argv, 0, stdout="INFO | something\nPixel_Tablet\nMedium_Phone\n", stderr=""
        ),
    )
    monkeypatch.setattr(emulator.time, "sleep", lambda s: None)
    return binario


def test_list_avds_skips_log_lines(emu):
    assert emulator.list_avds() == ["Pixel_Tablet", "Medium_Phone"]


def test_start_unknown_avd(emu):
    with pytest.raises(EmulatorError, match="does not exist"):
        emulator.start("Nope")


class FakeProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode


def test_start_returns_the_new_serial_after_boot(emu, monkeypatch):
    rodadas = iter(
        [
            [],  # before starting: no emulator
            [host.DeviceEntry("emulator-5554", "offline")],
            [host.DeviceEntry("emulator-5554", "device")],
        ]
    )
    monkeypatch.setattr(emulator.host, "devices", lambda: next(rodadas))
    lancados = []
    monkeypatch.setattr(
        emulator.subprocess, "Popen", lambda args, **k: lancados.append(args) or FakeProcess()
    )
    monkeypatch.setattr(emulator, "AdbClient", lambda serial: f"adb:{serial}")
    esperas = []
    monkeypatch.setattr(emulator, "wait_for_boot", lambda adb, timeout: esperas.append(adb))

    serial = emulator.start("Pixel_Tablet", headless=True, snapshot="limpo")

    assert serial == "emulator-5554"
    assert lancados[0][1:] == [
        "-avd",
        "Pixel_Tablet",
        "-no-window",
        "-no-audio",
        "-snapshot",
        "limpo",
    ]
    assert esperas == ["adb:emulator-5554"]


def test_start_reports_an_emulator_that_exits(emu, monkeypatch, tmp_path):
    monkeypatch.setattr(emulator.host, "devices", lambda: [])
    monkeypatch.setattr(emulator.subprocess, "Popen", lambda args, **k: FakeProcess(returncode=1))
    monkeypatch.setattr(emulator.tempfile, "gettempdir", lambda: str(tmp_path))
    with pytest.raises(EmulatorError, match="exited"):
        emulator.start("Pixel_Tablet")


def test_start_times_out_when_adb_never_sees_it(emu, monkeypatch):
    monkeypatch.setattr(emulator.host, "devices", lambda: [])
    monkeypatch.setattr(emulator.subprocess, "Popen", lambda args, **k: FakeProcess())
    with pytest.raises(DeviceTimeoutError):
        emulator.start("Pixel_Tablet", timeout=0)


def test_stop_only_emulators():
    with pytest.raises(EmulatorError):
        emulator.stop("RXCY103LPWT")


assert Path  # used in type hints of fixtures above


def test_start_retries_while_the_shell_is_closed(emu, monkeypatch):
    monkeypatch.setattr(
        emulator.host, "devices", iter([[], [host.DeviceEntry("emulator-5556", "device")]]).__next__
    )
    monkeypatch.setattr(emulator.subprocess, "Popen", lambda args, **k: FakeProcess())
    tentativas = []

    def adb_client(serial):
        tentativas.append(serial)
        if len(tentativas) < 3:
            raise DeviceNotFoundError("error: closed")
        return "adb-ok"

    monkeypatch.setattr(emulator, "AdbClient", adb_client)
    monkeypatch.setattr(emulator, "wait_for_boot", lambda adb, timeout: None)
    assert emulator.start("Pixel_Tablet") == "emulator-5556"
    assert len(tentativas) == 3


def test_adb_errors_become_adb_command_error(monkeypatch):
    from geppetto import AdbCommandError

    def falha(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv, output="", stderr="error: device not found")

    monkeypatch.setattr(host.subprocess, "run", falha)
    with pytest.raises(AdbCommandError, match="device not found"):
        host.run_adb("-s", "X", "emu", "kill")


def test_stop_a_stopped_emulator(monkeypatch):
    monkeypatch.setattr(emulator.host, "devices", lambda: [])
    with pytest.raises(EmulatorError, match="not running"):
        emulator.stop("emulator-5554")

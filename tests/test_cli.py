import json

import pytest

from geppetto import cli, doctor
from geppetto.core import host
from geppetto.doctor import Check, Status


@pytest.fixture
def aparelhos(monkeypatch):
    lista = [host.DeviceEntry("AAA", "device", {"model": "Pixel_8"})]
    monkeypatch.setattr(cli.host, "devices", lambda: lista)
    monkeypatch.delenv("GEPPETTO_SERIAL", raising=False)
    return lista


def test_devices_table_and_json(aparelhos, capsys):
    aparelhos.append(host.DeviceEntry("emulator-5554", "offline"))
    assert cli.main(["devices"]) == 0
    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0].split() == ["AAA", "device", "usb", "Pixel_8"]
    assert linhas[1].split() == ["emulator-5554", "offline", "emulator"]

    cli.main(["devices", "--json"])
    dados = json.loads(capsys.readouterr().out)
    assert dados[0]["serial"] == "AAA" and dados[0]["ready"] is True


def test_pick_serial(aparelhos, monkeypatch):
    assert cli.pick_serial(None) == "AAA"
    assert cli.pick_serial("XYZ") == "XYZ"
    monkeypatch.setenv("GEPPETTO_SERIAL", "ENV1,ENV2")
    assert cli.pick_serial(None) == "ENV1"
    monkeypatch.delenv("GEPPETTO_SERIAL")
    aparelhos.append(host.DeviceEntry("BBB", "device"))
    with pytest.raises(cli.CliError, match="choose one with -s"):
        cli.pick_serial(None)
    aparelhos.clear()
    with pytest.raises(cli.CliError, match="No device"):
        cli.pick_serial(None)


def test_doctor_prints_fixes_and_fails_on_errors(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.doctor,
        "run_checks",
        lambda serial=None: [
            Check("adb", Status.OK, "1.0.41"),
            Check("device X", Status.FAIL, "unauthorized", "Accept the prompt."),
        ],
    )
    assert cli.main(["doctor"]) == 1
    saida = capsys.readouterr().out
    assert "✔ adb: 1.0.41" in saida and "✘ device X: unauthorized" in saida
    assert "→ Accept the prompt." in saida


def test_doctor_device_checks():
    checks = doctor.check_devices(
        [
            host.DeviceEntry("U", "unauthorized"),
            host.DeviceEntry("O", "offline"),
            host.DeviceEntry("N", "not found"),
        ]
    )
    assert [c.status for c in checks] == [Status.FAIL] * 3
    assert all(c.fix for c in checks)
    assert "geppetto devices" in checks[2].fix
    assert doctor.check_devices([])[0].status is Status.WARN


def test_doctor_ready_device(monkeypatch):
    monkeypatch.setattr(doctor.host, "run_adb", lambda *a, **k: "1\n14\nPixel 8\n")
    ok, agente = doctor.check_ready_device(host.DeviceEntry("S", "device"))
    assert ok.status is Status.OK and "Pixel 8, Android 14" in ok.detail
    assert agente.status is Status.INFO and "first Device" in agente.fix


def test_shot_writes_the_png(aparelhos, monkeypatch, tmp_path, capsys):
    class FakeAdb:
        def __init__(self, serial):
            self.serial = serial

        def exec_out(self, command):
            return b"\x89PNG"

    monkeypatch.setattr(cli, "AdbClient", FakeAdb)
    destino = tmp_path / "sub" / "tela.png"
    assert cli.main(["shot", "-o", str(destino)]) == 0
    assert destino.read_bytes() == b"\x89PNG"
    assert capsys.readouterr().out.strip() == str(destino)


def test_errors_are_one_line_and_exit_1(monkeypatch, capsys):
    monkeypatch.setattr(cli.host, "devices", lambda: [])
    monkeypatch.delenv("GEPPETTO_SERIAL", raising=False)
    assert cli.main(["shot"]) == 1
    assert capsys.readouterr().err.startswith("geppetto: No device connected")


def test_pair_with_code(monkeypatch, capsys):
    pares = []
    monkeypatch.setattr(
        cli.host, "pair", lambda addr, code: pares.append((addr, code)) or "Successfully paired"
    )
    assert cli.main(["pair", "192.168.0.10:40111", "123456"]) == 0
    assert pares == [("192.168.0.10:40111", "123456")]


def test_pair_with_qr_finds_the_announced_service(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_qr_text", lambda payload: f"[QR {payload}]")
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    pareado = {}

    def servicos():
        nome = capsys.readouterr().out.split("S:")[1].split(";")[0]  # name inside the QR payload
        return [host.MdnsService(nome, "_adb-tls-pairing._tcp", "10.0.0.2:40000")]

    def pair(address, code):
        pareado.update(address=address, code=code)
        return "Successfully paired"

    monkeypatch.setattr(cli.host, "mdns_services", servicos)
    monkeypatch.setattr(cli.host, "pair", pair)
    assert cli.pair_with_qr(timeout=5) == "Successfully paired"
    assert pareado["address"] == "10.0.0.2:40000" and len(pareado["code"]) == 12


def test_qr_needs_the_extra(monkeypatch):
    import builtins

    original = builtins.__import__

    def sem_qrcode(name, *args, **kwargs):
        if name == "qrcode":
            raise ImportError
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sem_qrcode)
    with pytest.raises(cli.CliError, match=r"geppetto-android\[cli\]"):
        cli._qr_text("x")


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.startswith("geppetto ")


def test_doctor_does_not_fail_when_the_agent_is_missing(monkeypatch):
    comandos = []
    monkeypatch.setattr(
        doctor.host, "run_adb", lambda *a, **k: comandos.append(a[-1]) or "1\n14\nPixel\n"
    )
    doctor.check_ready_device(host.DeviceEntry("S", "device"))
    assert comandos[0].endswith("|| true")  # `ls` of a missing agent exits 1 and failed the check

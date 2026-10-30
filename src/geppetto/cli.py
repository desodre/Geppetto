"""``geppetto`` command line: everyday lab tasks without writing Python.

    geppetto devices [--json]
    geppetto doctor [-s SERIAL] [--json]
    geppetto shot [-s SERIAL] [-o FILE]
    geppetto record [-s SERIAL] [-o FILE] [-t SECONDS]      (Ctrl+C stops earlier)
    geppetto emulator list | start AVD [--headless] [--snapshot NAME] [--wipe-data] [--no-wait]
                     | stop SERIAL | snapshot {save,load,list} [NAME] -s SERIAL
    geppetto pair HOST:PORT [CODE] | pair --qr
    geppetto connect HOST:PORT | disconnect HOST:PORT
    geppetto inspect [-s SERIAL] [--port 8765] [--host 127.0.0.1] [--no-browser]

Commands that need one device take ``-s/--serial``, then ``GEPPETTO_SERIAL``, then the only ready
device. Exit codes: 0 ok, 1 failure (message on stderr), 2 usage error, 130 interrupted.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import secrets
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import __version__, doctor
from .core import emulator, host
from .core.adb import AdbClient
from .exceptions import GeppettoError
from .recording import MAX_SECONDS, ScreenRecording

SYMBOL = {
    doctor.Status.OK: "✔",
    doctor.Status.WARN: "⚠",
    doctor.Status.FAIL: "✘",
    doctor.Status.INFO: "·",
}


class CliError(GeppettoError):
    """A user-facing error: printed without a traceback, exit code 1."""


def _out(text: str = "") -> None:
    print(text, flush=True)


def pick_serial(serial: str | None) -> str:
    """``--serial``, then ``GEPPETTO_SERIAL``, then the only ready device."""
    chosen = serial or os.environ.get("GEPPETTO_SERIAL", "").split(",")[0].strip()
    if chosen:
        return chosen
    ready = [e.serial for e in host.devices() if e.ready]
    if len(ready) == 1:
        return ready[0]
    if not ready:
        raise CliError("No device connected. Run `geppetto doctor` to see why.")
    raise CliError(
        f"{len(ready)} devices connected ({', '.join(ready)}): choose one with -s SERIAL."
    )


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── devices / doctor ─────────────────────────────────────────────────


def cmd_devices(args: argparse.Namespace) -> int:
    entries = host.devices()
    if args.json:
        _out(json.dumps([{**asdict(e), "ready": e.ready} for e in entries], indent=2))
        return 0
    if not entries:
        _out("No devices. Run `geppetto doctor` for help.")
        return 0
    largura = max(len(e.serial) for e in entries)
    for e in entries:
        tipo = "emulator" if e.is_emulator else "wi-fi" if e.is_wireless else "usb"
        _out(f"{e.serial:<{largura}}  {e.state:<12}  {tipo:<8}  {e.model}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = doctor.run_checks(args.serial)
    if args.json:
        _out(json.dumps([{**asdict(c), "status": c.status.value} for c in checks], indent=2))
    else:
        for c in checks:
            _out(f"{SYMBOL[c.status]} {c.name}: {c.detail}")
            if c.fix and c.status is not doctor.Status.OK:
                _out(f"    → {c.fix}")
    return 1 if any(c.status is doctor.Status.FAIL for c in checks) else 0


# ── shot / record ────────────────────────────────────────────────────


def cmd_shot(args: argparse.Namespace) -> int:
    serial = pick_serial(args.serial)
    path = Path(args.output or f"screenshot_{serial.replace(':', '_')}_{_stamp()}.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(AdbClient(serial).exec_out("screencap -p"))
    _out(str(path))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    serial = pick_serial(args.serial)
    path = Path(args.output or f"screenrecord_{serial.replace(':', '_')}_{_stamp()}.mp4")
    path.parent.mkdir(parents=True, exist_ok=True)
    limite = min(args.time, MAX_SECONDS)
    gravacao = ScreenRecording(AdbClient(serial), f"geppetto_cli_{_stamp()}", limite).start()
    _out(f"Recording {serial} for up to {limite}s… Ctrl+C to stop.")
    fim = time.monotonic() + limite
    try:
        while gravacao.running and time.monotonic() < fim:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass  # stop below and keep what was recorded
    _out(gravacao.stop(path))
    return 0


# ── emulator ─────────────────────────────────────────────────────────


def cmd_emulator(args: argparse.Namespace) -> int:
    if args.emulator_cmd == "list":
        avds, ativos = emulator.list_avds(), emulator.running()
        if not avds:
            _out("No AVD. Create one in Android Studio › Device Manager.")
        for avd in avds:
            seriais = [s for s, nome in ativos.items() if nome == avd]
            _out(f"{avd}  {'running: ' + ', '.join(seriais) if seriais else 'stopped'}")
        return 0
    if args.emulator_cmd == "start":
        _out(f"Starting {args.avd}…" + ("" if args.no_wait else " (waiting for the boot)"))
        serial = emulator.start(
            args.avd,
            headless=args.headless,
            snapshot=args.snapshot,
            wipe_data=args.wipe_data,
            wait=not args.no_wait,
            timeout=args.timeout,
        )
        _out(serial)
        return 0
    if args.emulator_cmd == "stop":
        emulator.stop(args.serial)
        _out(f"Stopped {args.serial}")
        return 0
    serial = pick_serial(args.serial)  # snapshot
    if args.action == "list":
        _out(emulator.snapshot_list(serial))
        return 0
    if not args.name:
        raise CliError(f"snapshot {args.action} needs a NAME")
    acao = emulator.snapshot_save if args.action == "save" else emulator.snapshot_load
    _out(acao(serial, args.name) or "OK")
    return 0


# ── Wi-Fi pairing ────────────────────────────────────────────────────


def _qr_text(payload: str) -> str:
    try:
        import qrcode  # type: ignore[import-untyped]
    except ImportError:
        raise CliError(
            "QR pairing needs the `qrcode` package: pip install 'geppetto-android[cli]'. "
            "Or pair with a code: `geppetto pair HOST:PORT CODE`."
        ) from None
    qr = qrcode.QRCode(border=1)
    qr.add_data(payload)
    buffer = io.StringIO()
    qr.print_ascii(out=buffer, invert=True)
    return buffer.getvalue()


def pair_with_qr(timeout: float = 120) -> str:
    """Show a QR code for *Wireless debugging › Pair device with QR code* and pair the phone.

    Android scans ``WIFI:T:ADB;S:<name>;P:<password>;;`` and then announces an mDNS pairing service
    with that name; we find it and run ``adb pair``.
    """
    nome = f"geppetto-{secrets.token_hex(3)}"
    senha = secrets.token_hex(6)
    _out(_qr_text(f"WIFI:T:ADB;S:{nome};P:{senha};;"))
    _out("On the phone: Developer options › Wireless debugging › Pair device with QR code.")
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        for servico in host.mdns_services():
            if servico.is_pairing and servico.name == nome:
                return host.pair(servico.address, senha)
        time.sleep(1)
    raise CliError("The phone did not show up for pairing (same Wi-Fi network? mDNS allowed?).")


def cmd_pair(args: argparse.Namespace) -> int:
    if args.qr:
        _out(pair_with_qr(args.timeout))
    else:
        if not args.address:
            raise CliError(
                "pair needs HOST:PORT (shown under 'Pair device with pairing code') or --qr"
            )
        code = args.code or input("Pairing code: ").strip()
        _out(host.pair(args.address, code))
    _out(
        "Now connect with `geppetto connect HOST:PORT` (the port on the Wireless debugging screen)."
    )
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    _out(host.connect(args.address))
    return 0


def cmd_disconnect(args: argparse.Namespace) -> int:
    _out(host.disconnect(args.address))
    return 0


# ── inspector ────────────────────────────────────────────────────────


def cmd_inspect(args: argparse.Namespace) -> int:
    from .device import Device  # uiautomator2: only for this command
    from .inspector import InspectorServer

    serial = pick_serial(args.serial)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"geppetto: warning: listening on {args.host}: anyone who reaches this port can tap "
            "and type on the device.",
            file=sys.stderr,
        )
    _out(f"Connecting to {serial} (installs the uiautomator2 agent on first use)…")
    device = Device(serial, output_dir=args.output, log_to_console=False)
    server = InspectorServer(device, host=args.host, port=args.port)
    _out(f"Geppetto Inspector on {server.url}  (Ctrl+C to stop)")
    if not args.no_browser:
        import webbrowser

        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    if server.recorder.steps:
        _out("\nRecorded script:\n")
        _out(server.recorder.script())
    return 0


# ── parser ───────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="geppetto", description="Android device lab helper.")
    parser.add_argument("--version", action="version", version=f"geppetto {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def serial_opt(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "-s", "--serial", help="device serial (default: GEPPETTO_SERIAL or the only device)"
        )

    p = sub.add_parser("devices", help="list devices adb knows")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser("doctor", help="check adb, devices, emulator and extras, with fixes")
    p.add_argument("-s", "--serial", help="inspect only this device")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("shot", help="save a screenshot")
    serial_opt(p)
    p.add_argument("-o", "--output", help="PNG path (default: screenshot_<serial>_<time>.png)")
    p.set_defaults(func=cmd_shot)

    p = sub.add_parser("record", help="record the screen (Ctrl+C to stop)")
    serial_opt(p)
    p.add_argument("-o", "--output", help="MP4 path (default: screenrecord_<serial>_<time>.mp4)")
    p.add_argument(
        "-t", "--time", type=int, default=MAX_SECONDS, help=f"seconds, max {MAX_SECONDS}"
    )
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("emulator", help="manage Android emulators")
    p.set_defaults(func=cmd_emulator)
    esub = p.add_subparsers(dest="emulator_cmd", required=True, metavar="ACTION")
    esub.add_parser("list", help="AVDs and which are running")
    start = esub.add_parser("start", help="start an AVD and wait for the boot")
    start.add_argument("avd")
    start.add_argument("--headless", action="store_true", help="no window, no audio")
    start.add_argument("--snapshot", help="boot from this snapshot")
    start.add_argument("--wipe-data", action="store_true")
    start.add_argument(
        "--no-wait", action="store_true", help="return when adb sees it, before the boot"
    )
    start.add_argument("--timeout", type=float, default=300)
    stop = esub.add_parser("stop", help="shut down an emulator")
    stop.add_argument("serial")
    snap = esub.add_parser("snapshot", help="save, load or list snapshots")
    snap.add_argument("action", choices=("save", "load", "list"))
    snap.add_argument("name", nargs="?")
    serial_opt(snap)

    p = sub.add_parser("pair", help="pair a phone over Wi-Fi (Android 11+)")
    p.add_argument("address", nargs="?", help="HOST:PORT from 'Pair device with pairing code'")
    p.add_argument("code", nargs="?", help="the 6-digit code (asked if omitted)")
    p.add_argument("--qr", action="store_true", help="show a QR code to scan instead")
    p.add_argument("--timeout", type=float, default=120)
    p.set_defaults(func=cmd_pair)

    p = sub.add_parser("inspect", help="screen, hierarchy and selectors in a browser; record code")
    serial_opt(p)
    p.add_argument("--port", type=int, default=8765, help="0 picks a free port (default 8765)")
    p.add_argument("--host", default="127.0.0.1", help="interface to listen on (default: local)")
    p.add_argument("--no-browser", action="store_true", help="do not open the browser")
    p.add_argument("-o", "--output", default="./results", help="Device result folder")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("connect", help="adb connect HOST:PORT")
    p.add_argument("address")
    p.set_defaults(func=cmd_connect)

    p = sub.add_parser("disconnect", help="adb disconnect HOST:PORT")
    p.add_argument("address")
    p.set_defaults(func=cmd_disconnect)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except GeppettoError as erro:
        print(f"geppetto: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

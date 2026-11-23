"""The Carlo backend: protocol v1 codec, control client, device session, Device and doctor.

No device and no Carlo binary are needed: the agent side is a small in-process fake speaking
the real wire format over a socketpair or loopback TCP, adb goes through ``AdbRecorder`` and
``adb shell carlo serve`` is a fake ``Popen`` whose stdout is a real pipe.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shlex
import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from geppetto import By, CarloError, Device, DeviceTimeoutError, doctor
from geppetto.core import adb as adb_module
from geppetto.core.adb import AdbClient
from geppetto.core.backend import CarloBackend, create_backend
from geppetto.core.carlo import (
    BINARY_ENV,
    BULK_LIMIT,
    CONTROL,
    CONTROL_LIMIT,
    HEADER,
    HIERARCHY,
    MAGIC,
    VIDEO,
    CarloControlClient,
    CarloSession,
    Frame,
    VideoPacket,
    decode_video_packet,
    encode_frame,
    encode_video_packet,
    parse_wm_size,
    read_frame,
)
from geppetto.doctor import Status
from geppetto.ui.window_dump import WindowDump

from .conftest import DUMP, AdbRecorder

#: Copies of Carlo's shared vectors (tests/fixtures in the Carlo repository).
FIXTURES = Path(__file__).parent / "fixtures" / "carlo"
FRAMES = json.loads((FIXTURES / "protocol_frames.json").read_text())["frames"]
PACKETS = json.loads((FIXTURES / "video_packets.json").read_text())["packets"]

TOKEN = "0123456789abcdef" * 2
ABSTRACT_NAME = "carlo-" + "ab" * 16
SERIAL = "SERIAL123"


class OneByteReader:
    """A stream that hands out at most one byte per ``read`` (worst-case socket)."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def read(self, size: int, /) -> bytes:
        chunk = self.data[self.pos : self.pos + min(size, 1)]
        self.pos += len(chunk)
        return chunk


def _raw_frame(kind: int, request_id: int, payload: bytes, version: int = 1) -> bytes:
    """A frame built without :func:`encode_frame`'s checks (for kinds it refuses)."""
    return HEADER.pack(MAGIC, version, kind, 0, request_id, len(payload)) + payload


# ── Framing ──────────────────────────────────────────────────────────


VALID_FRAMES = [f for f in FRAMES if "error" not in f]
INVALID_FRAMES = [f for f in FRAMES if "error" in f]


@pytest.mark.parametrize("vector", VALID_FRAMES, ids=lambda v: v["name"])
def test_shared_frame_vectors_round_trip(vector):
    wire = bytes.fromhex(vector["hex"])
    payload = bytes.fromhex(vector["payload_hex"])
    assert encode_frame(vector["kind"], vector["request_id"], payload) == wire
    reader = OneByteReader(wire)
    assert read_frame(reader) == Frame(vector["kind"], vector["request_id"], payload)
    assert read_frame(reader) is None


@pytest.mark.parametrize("vector", INVALID_FRAMES, ids=lambda v: v["name"])
def test_shared_invalid_frame_vectors_raise_their_code(vector):
    wire = bytes.fromhex(vector["hex"])
    reader = OneByteReader(wire)
    with pytest.raises(CarloError) as raised:
        read_frame(reader)
    assert raised.value.code == vector["error"]
    if vector["recoverable"]:
        assert reader.pos == len(wire)  # the payload was consumed: the stream is still usable


def test_unknown_kind_leaves_the_next_frame_readable():
    ping = encode_frame(CONTROL, 7, b'{"command":"ping"}')
    reader = OneByteReader(_raw_frame(9, 5, b"ab") + ping)
    with pytest.raises(CarloError, match="kind 9") as raised:
        read_frame(reader)
    assert raised.value.code == "unknown_kind"
    assert read_frame(reader) == Frame(CONTROL, 7, b'{"command":"ping"}')


@pytest.mark.parametrize(
    ("header", "code"),
    [
        (HEADER.pack(b"HTTP", 1, CONTROL, 0, 1, 2), "bad_magic"),
        (HEADER.pack(MAGIC, 2, CONTROL, 0, 1, 2), "unsupported_version"),
        (HEADER.pack(MAGIC, 1, CONTROL, 1, 1, 2), "reserved_bits"),
        (HEADER.pack(MAGIC, 1, CONTROL, 0x8000, 1, 2), "reserved_bits"),
        (HEADER.pack(MAGIC, 1, CONTROL, 0, 1, CONTROL_LIMIT + 1), "frame_too_large"),
        (HEADER.pack(MAGIC, 1, HIERARCHY, 0, 1, BULK_LIMIT + 1), "frame_too_large"),
        (HEADER.pack(MAGIC, 1, VIDEO, 0, 1, 0xFFFFFFFF), "frame_too_large"),
        (HEADER.pack(MAGIC, 1, 9, 0, 1, BULK_LIMIT + 1), "frame_too_large"),
    ],
)
def test_header_is_rejected_before_any_payload_byte_is_read(header, code):
    reader = OneByteReader(header + b"payload that must not be read")
    with pytest.raises(CarloError) as raised:
        read_frame(reader)
    assert raised.value.code == code
    assert reader.pos == HEADER.size


def test_limits_are_inclusive():
    control = b"x" * CONTROL_LIMIT
    frame = encode_frame(CONTROL, 1, control)
    assert read_frame(OneByteReader(frame)) == Frame(CONTROL, 1, control)
    bulk = b"x" * (CONTROL_LIMIT + 1)  # too big for control, fine for a hierarchy
    frame = encode_frame(HIERARCHY, 2, bulk)
    assert read_frame(OneByteReader(frame)) == Frame(HIERARCHY, 2, bulk)


def test_end_of_stream():
    assert read_frame(OneByteReader(b"")) is None
    with pytest.raises(CarloError) as raised:
        read_frame(OneByteReader(MAGIC + b"\x01"))
    assert raised.value.code == "truncated_frame"
    with pytest.raises(CarloError) as raised:
        read_frame(OneByteReader(encode_frame(CONTROL, 1, b"{}")[:-1]))
    assert raised.value.code == "truncated_frame"


@pytest.mark.parametrize(
    ("kind", "request_id", "payload", "code"),
    [
        (9, 1, b"", "unknown_kind"),
        (CONTROL, -1, b"", "invalid_request"),
        (CONTROL, 2**32, b"", "invalid_request"),
        (CONTROL, 1, b"x" * (CONTROL_LIMIT + 1), "frame_too_large"),
    ],
)
def test_encode_frame_refuses_what_the_agent_would_reject(kind, request_id, payload, code):
    with pytest.raises(CarloError) as raised:
        encode_frame(kind, request_id, payload)
    assert raised.value.code == code


VALID_PACKETS = [p for p in PACKETS if "error" not in p]
INVALID_PACKETS = [p for p in PACKETS if "error" in p]


@pytest.mark.parametrize("vector", VALID_PACKETS, ids=lambda v: v["name"])
def test_shared_video_packet_vectors_round_trip(vector):
    payload = bytes.fromhex(vector["payload_hex"])
    packet = decode_video_packet(payload)
    assert packet == VideoPacket(
        vector["type"],
        vector["key_frame"],
        vector["generation"],
        vector["pts_us"],
        vector["width"],
        vector["height"],
        bytes.fromhex(vector["data_hex"]),
    )
    assert encode_video_packet(packet) == payload


@pytest.mark.parametrize("vector", INVALID_PACKETS, ids=lambda v: v["name"])
def test_shared_invalid_video_packet_vectors_raise_their_code(vector):
    with pytest.raises(CarloError) as raised:
        decode_video_packet(bytes.fromhex(vector["payload_hex"]))
    assert raised.value.code == vector["error"]


def test_encode_video_packet_refuses_fields_that_do_not_fit():
    with pytest.raises(CarloError) as raised:
        encode_video_packet(VideoPacket(2, True, 1, 0, 70_000, 640, b"\x00"))
    assert raised.value.code == "invalid_packet"


# ── wm size ──────────────────────────────────────────────────────────


def test_parse_wm_size_physical():
    assert parse_wm_size("Physical size: 1080x2340\n") == (1080, 2340)


def test_parse_wm_size_prefers_the_override():
    output = "Physical size: 1080x2340\nOverride size: 720x1560\n"
    assert parse_wm_size(output) == (720, 1560)


@pytest.mark.parametrize("output", ["", "error: no devices", "Physical size: unknown"])
def test_parse_wm_size_error(output):
    with pytest.raises(CarloError) as raised:
        parse_wm_size(output)
    assert raised.value.code == "invalid_wm_size"


# ── Fake agent ───────────────────────────────────────────────────────

#: request ID → raw bytes to send back (``b""`` sends nothing, ``None`` closes the connection).
Reply = Callable[[int], bytes | None]


def ok(request_id: int, **fields: object) -> bytes:
    body = json.dumps({"ok": True, **fields}).encode()
    return encode_frame(CONTROL, request_id, body)


def refused(request_id: int, code: str) -> bytes:
    body = json.dumps({"ok": False, "error": {"code": code, "message": "refused"}}).encode()
    return encode_frame(CONTROL, request_id, body)


def hierarchy(xml: str) -> Reply:
    return lambda rid: encode_frame(HIERARCHY, rid, xml.encode())


CAPABILITIES = [{"name": "hierarchy", "available": True, "reason": None}]
HELLO = {"command": "hello", "protocol": 1, "session": TOKEN}

DEFAULT_REPLIES: dict[str, Reply] = {
    "hello": lambda rid: ok(rid, agent={"name": "carlo"}, device={"sdk": 36}),
    "ping": lambda rid: ok(rid),
    "capabilities": lambda rid: ok(rid, capabilities=CAPABILITIES),
    "channels": lambda rid: ok(rid, video="absent"),
    "hierarchy.dump": hierarchy(DUMP),
    "shutdown": lambda rid: ok(rid),
}


class FakeAgent:
    """The agent side of the control channel, served in a thread on one connected socket.

    *replies* overrides :data:`DEFAULT_REPLIES` and is read live, so a test can change an
    answer after the connection is up.
    """

    def __init__(
        self,
        conn: socket.socket,
        replies: dict[str, Reply] | None = None,
        requests: list[tuple[int, dict[str, object]]] | None = None,
    ) -> None:
        self.conn = conn
        self.replies = replies if replies is not None else {}
        self.requests = requests if requests is not None else []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        reader = self.conn.makefile("rb")
        try:
            while (frame := read_frame(reader)) is not None:
                message = json.loads(frame.payload)
                self.requests.append((frame.request_id, message))
                command = message["command"]
                reply = self.replies.get(command, DEFAULT_REPLIES[command])(frame.request_id)
                if reply is None:
                    return
                self.conn.sendall(reply)
                if command == "shutdown":
                    return
        except (OSError, CarloError):
            return
        finally:
            reader.close()
            self.conn.close()

    @property
    def commands(self) -> list[object]:
        return [message["command"] for _, message in self.requests]


def connect(
    replies: dict[str, Reply] | None = None, timeout: float = 2.0
) -> tuple[CarloControlClient, FakeAgent]:
    host_end, agent_end = socket.socketpair()
    return CarloControlClient(host_end, timeout=timeout), FakeAgent(agent_end, replies)


# ── Control client ───────────────────────────────────────────────────


def test_control_commands_round_trip():
    client, agent = connect()
    try:
        assert client.hello(TOKEN)["agent"] == {"name": "carlo"}
        client.ping()
        assert client.capabilities() == CAPABILITIES
        assert client.channels() == "absent"
    finally:
        client.close()
    assert agent.requests == [
        (1, HELLO),
        (2, {"command": "ping"}),
        (3, {"command": "capabilities"}),
        (4, {"command": "channels"}),
    ]


def test_hierarchy_dump_is_a_raw_utf8_xml_frame():
    xml = DUMP.replace("Don't allow", "Não permitir 🪵")
    client, _ = connect({"hierarchy.dump": hierarchy(xml)})
    try:
        dump = client.hierarchy_dump()
    finally:
        client.close()
    assert dump == xml
    widgets = WindowDump(dump)
    assert widgets.find_widget(By.ID, "com.app:id/deny").text == "Não permitir 🪵"
    assert widgets.find_widget(By.TEXT, "Login").id == "com.app:id/login"


@pytest.mark.parametrize("code", ["unavailable", "conflict", "truncated"])
def test_agent_errors_raise_their_code_and_keep_the_connection(code):
    client, _ = connect({"hierarchy.dump": lambda rid: refused(rid, code)})
    try:
        with pytest.raises(CarloError) as raised:
            client.hierarchy_dump()
        assert raised.value.code == code
        client.ping()  # an ``ok: false`` answer does not desynchronise the stream
    finally:
        client.close()


def test_hierarchy_dump_needs_a_hierarchy():
    client, _ = connect({"hierarchy.dump": lambda rid: ok(rid)})
    try:
        with pytest.raises(CarloError) as raised:
            client.hierarchy_dump()
        assert raised.value.code == "invalid_response"
    finally:
        client.close()


def test_hierarchy_dump_must_be_utf8():
    client, _ = connect({"hierarchy.dump": lambda rid: encode_frame(HIERARCHY, rid, b"\xff")})
    try:
        with pytest.raises(CarloError) as raised:
            client.hierarchy_dump()
        assert raised.value.code == "invalid_response"
    finally:
        client.close()


def test_unexpected_kind_on_a_control_command():
    client, _ = connect({"ping": hierarchy("<hierarchy/>")})
    try:
        with pytest.raises(CarloError) as raised:
            client.ping()
        assert raised.value.code == "unexpected_kind"
    finally:
        client.close()


def test_unknown_kind_frames_are_skipped():
    client, _ = connect({"ping": lambda rid: _raw_frame(9, rid, b"ab") + ok(rid)})
    try:
        client.ping()
    finally:
        client.close()


def _closed_after(client: CarloControlClient) -> None:
    with pytest.raises(CarloError) as raised:
        client.ping()
    assert raised.value.code == "closed"


def test_framing_rejection_desynchronises_the_client():
    rejection = b'{"error":{"code":"frame_too_large","limit":65536}}'
    client, _ = connect({"ping": lambda rid: encode_frame(CONTROL, 0, rejection)})
    try:
        with pytest.raises(CarloError) as raised:
            client.ping()
        assert raised.value.code == "frame_too_large"
        _closed_after(client)
    finally:
        client.close()


def test_response_must_echo_the_request_id():
    client, _ = connect({"ping": lambda rid: ok(rid + 1)})
    try:
        with pytest.raises(CarloError) as raised:
            client.ping()
        assert raised.value.code == "invalid_response"
        _closed_after(client)
    finally:
        client.close()


def test_hierarchy_dump_has_its_own_longer_timeout():
    def slow_dump(rid: int) -> bytes | None:
        threading.Event().wait(0.4)
        return hierarchy(DUMP)(rid)

    host_end, agent_end = socket.socketpair()
    client = CarloControlClient(host_end, timeout=0.2, hierarchy_timeout=2.0)
    FakeAgent(agent_end, {"hierarchy.dump": slow_dump})
    try:
        assert client.hierarchy_dump() == DUMP
        client.ping()  # a slow valid dump does not poison the client
    finally:
        client.close()


def test_silent_agent_times_out():
    client, _ = connect({"ping": lambda rid: b""}, timeout=0.2)
    try:
        with pytest.raises(CarloError) as raised:
            client.ping()
        assert raised.value.code == "timeout"
        _closed_after(client)
    finally:
        client.close()


def test_agent_closing_the_connection():
    client, _ = connect({"ping": lambda rid: None})
    try:
        with pytest.raises(CarloError) as raised:
            client.ping()
        assert raised.value.code == "closed"
    finally:
        client.close()


def test_shutdown_ends_the_connection():
    client, agent = connect()
    try:
        client.shutdown()
        _closed_after(client)
    finally:
        client.close()
    assert agent.commands == ["shutdown"]


# ── Device session ───────────────────────────────────────────────────


class FakeProcess:
    """``adb shell carlo serve``: its stdout is a real pipe holding *output*."""

    pid = 4242

    def __init__(self, output: bytes, exit_code: int = 0, keep_open: bool = False) -> None:
        read_end, self._write_end = os.pipe()
        os.write(self._write_end, output)
        if not keep_open:
            self._close_writer()
        self.stdout = os.fdopen(read_end, "r")
        self.exit_code = exit_code

    def _close_writer(self) -> None:
        if self._write_end is not None:
            os.close(self._write_end)
            self._write_end = None

    def wait(self, timeout: float | None = None) -> int:
        self._close_writer()
        return self.exit_code

    def terminate(self) -> None:
        self._close_writer()

    kill = terminate


class AgentServer:
    """A loopback TCP port standing in for ``adb forward``; serves one fake agent."""

    def __init__(self) -> None:
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port: int = self.listener.getsockname()[1]
        self.replies: dict[str, Reply] = {}
        self.requests: list[tuple[int, dict[str, object]]] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        try:
            conn, _ = self.listener.accept()
        except OSError:
            return
        FakeAgent(conn, self.replies, self.requests)

    @property
    def commands(self) -> list[object]:
        return [message["command"] for _, message in self.requests]


def ready_line(transport: str, session_dir: str, session: str = TOKEN) -> bytes:
    name = f"{session_dir}/control.sock" if transport == "filesystem" else ABSTRACT_NAME
    ready = {
        "ready": True,
        "protocol": 1,
        "transport": transport,
        "socket": name,
        "session": session,
    }
    return json.dumps(ready).encode() + b"\n"


class CarloHarness:
    """adb answers (serial, forward, wm size), ``Popen`` and the agent behind the forward."""

    def __init__(self, adb_run: AdbRecorder, monkeypatch: pytest.MonkeyPatch, tmp: Path):
        self.adb_run = adb_run
        self.binary = tmp / "carlo"
        self.binary.write_bytes(b"\x7fELF fake carlo")
        self.server = AgentServer()
        self.transport = "filesystem"
        self.ready: Callable[[str], bytes] = lambda d: ready_line(self.transport, d)
        self.exit_code = 0
        self.keep_open = False
        self.wm_size = "Physical size: 1080x2340\n"
        self.forward_error: Exception | None = None
        self.popen_argv: list[list[str]] = []
        self.processes: list[FakeProcess] = []
        adb_run.responder = self.respond
        monkeypatch.setattr(adb_module.subprocess, "Popen", self.popen)

    def respond(self, argv: list[str]) -> str:
        if argv[3:] == ["shell", "getprop ro.serialno"]:
            return f"{SERIAL}\n"
        if argv[3:5] == ["forward", "tcp:0"]:
            if self.forward_error is not None:
                raise self.forward_error
            return f"{self.server.port}\n"
        if argv[3:] == ["shell", "wm size"]:
            return self.wm_size
        return ""

    def popen(self, argv: list[str], **kwargs: object) -> FakeProcess:
        self.popen_argv.append(argv)
        session_dir = shlex.split(argv[4])[-1]
        process = FakeProcess(self.ready(session_dir), self.exit_code, self.keep_open)
        self.processes.append(process)
        return process

    @property
    def calls(self) -> list[list[str]]:
        """adb calls after the client's serial check."""
        return [c for c in self.adb_run.calls if c[3:] != ["shell", "getprop ro.serialno"]]


@pytest.fixture
def carlo(adb_run, monkeypatch, tmp_path) -> Iterator[CarloHarness]:
    monkeypatch.delenv(BINARY_ENV, raising=False)
    harness = CarloHarness(adb_run, monkeypatch, tmp_path)
    yield harness
    harness.server.listener.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cleanup_calls(session_dir: str, port: int | None) -> list[list[str]]:
    forward = [["adb", "-s", SERIAL, "forward", "--remove", f"tcp:{port}"]] if port else []
    return [*forward, ["adb", "-s", SERIAL, "shell", f"rm -rf {session_dir}"]]


@pytest.mark.parametrize(
    ("transport", "target"),
    [
        ("filesystem", "localfilesystem:{dir}/control.sock"),
        ("abstract", "localabstract:{name}"),
    ],
)
def test_session_lifecycle(carlo, adb, transport, target):
    carlo.transport = transport
    session = CarloSession(adb, carlo.binary, sha256=_sha256(carlo.binary))
    d = session.session_dir
    assert d.startswith("/data/local/tmp/geppetto-carlo-")

    assert session.start() is session
    port = session.port
    assert session.hello_info["device"] == {"sdk": 36}
    assert session.client.hierarchy_dump() == DUMP
    serve = f"{d}/carlo serve --session-dir {d}"
    assert carlo.popen_argv == [["adb", "-s", SERIAL, "shell", serve]]
    assert carlo.calls == [
        ["adb", "-s", SERIAL, "shell", f"mkdir -m 700 {d}"],
        ["adb", "-s", SERIAL, "push", str(carlo.binary), f"{d}/carlo"],
        ["adb", "-s", SERIAL, "shell", f"chmod 700 {d}/carlo"],
        ["adb", "-s", SERIAL, "forward", "tcp:0", target.format(dir=d, name=ABSTRACT_NAME)],
    ]

    carlo.adb_run.calls.clear()
    session.close()
    assert carlo.calls == _cleanup_calls(d, port)
    assert carlo.server.requests[0] == (1, HELLO)
    assert carlo.server.commands == ["hello", "hierarchy.dump", "shutdown"]
    assert carlo.processes[0].stdout.closed
    with pytest.raises(CarloError) as raised:
        session.client  # noqa: B018 — the property raises
    assert raised.value.code == "not_started"

    carlo.adb_run.calls.clear()
    session.close()  # idempotent
    assert carlo.calls == []


def test_session_is_a_context_manager_and_reads_the_binary_from_the_environment(
    carlo, adb, monkeypatch
):
    monkeypatch.setenv(BINARY_ENV, str(carlo.binary))
    with CarloSession(adb) as session:
        session.client.ping()
        d = session.session_dir
    assert ["adb", "-s", SERIAL, "push", str(carlo.binary), f"{d}/carlo"] in carlo.calls
    assert carlo.calls[-1] == ["adb", "-s", SERIAL, "shell", f"rm -rf {d}"]
    assert carlo.server.commands == ["hello", "ping", "shutdown"]


def test_checksum_accepts_any_case_and_whitespace(carlo, adb):
    digest = f"  {_sha256(carlo.binary).upper()}\n"
    CarloSession(adb, carlo.binary, sha256=digest).start().close()


def test_checksum_mismatch_touches_nothing(carlo, adb):
    session = CarloSession(adb, carlo.binary, sha256="00" * 32)
    with pytest.raises(CarloError) as raised:
        session.start()
    assert raised.value.code == "checksum_mismatch"
    assert carlo.calls == []
    assert carlo.popen_argv == []


@pytest.mark.parametrize("binary", [None, "/nowhere/carlo"])
def test_missing_binary(carlo, adb, binary):
    with pytest.raises(CarloError) as raised:
        CarloSession(adb, binary).start()
    assert raised.value.code == "binary_missing"
    assert carlo.calls == []


def test_handshake_failure_cleans_everything_up(carlo, adb):
    carlo.server.replies["hello"] = lambda rid: refused(rid, "invalid_session")
    session = CarloSession(adb, carlo.binary)
    with pytest.raises(CarloError) as raised:
        session.start()
    assert raised.value.code == "invalid_session"
    port = carlo.server.port
    assert carlo.calls[-2:] == _cleanup_calls(session.session_dir, port)
    assert session.port is None
    assert carlo.processes[0].stdout.closed
    with pytest.raises(CarloError):
        session.client  # noqa: B018 — the property raises


def test_forward_failure_cleans_up(carlo, adb):
    carlo.forward_error = subprocess.CalledProcessError(1, "adb forward")
    session = CarloSession(adb, carlo.binary)
    with pytest.raises(CarloError) as raised:
        session.start()
    assert raised.value.code == "adb"
    assert carlo.calls[-1] == ["adb", "-s", SERIAL, "shell", f"rm -rf {session.session_dir}"]
    assert carlo.processes[0].stdout.closed


def test_adb_timeout_during_start_is_a_timeout_and_cleans_up(carlo, adb):
    carlo.forward_error = subprocess.TimeoutExpired("adb forward", 30)
    session = CarloSession(adb, carlo.binary)
    with pytest.raises(CarloError) as raised:
        session.start()
    assert raised.value.code == "timeout"
    assert carlo.calls[-1] == ["adb", "-s", SERIAL, "shell", f"rm -rf {session.session_dir}"]
    assert carlo.processes[0].stdout.closed


def test_adb_timeout_during_cleanup_never_raises(carlo, adb, caplog):
    session = CarloSession(adb, carlo.binary).start()
    session_dir, port = session.session_dir, session.port
    respond = carlo.respond

    def hang_on_cleanup(argv: list[str]) -> str:
        if argv[3:5] == ["forward", "--remove"] or argv[3:] == ["shell", f"rm -rf {session_dir}"]:
            raise subprocess.TimeoutExpired(argv, 30)
        return respond(argv)

    carlo.adb_run.responder = hang_on_cleanup
    with caplog.at_level(logging.WARNING):
        session.close()
    assert carlo.calls[-2:] == _cleanup_calls(session_dir, port)
    assert "Could not remove the Carlo forward" in caplog.text
    assert f"Could not remove {session_dir}" in caplog.text
    assert session.port is None


def _other_protocol(session_dir: str) -> bytes:
    return ready_line("filesystem", session_dir).replace(b'"protocol": 1', b'"protocol": 2')


@pytest.mark.parametrize(
    ("ready", "code"),
    [
        (lambda d: b"not json\n", "invalid_ready"),
        (lambda d: b'{"ready": false}\n', "invalid_ready"),
        (lambda d: ready_line("filesystem", "/data/local/tmp/other"), "invalid_ready"),
        (lambda d: ready_line("filesystem", d, session="short"), "invalid_ready"),
        (lambda d: ready_line("tcp", d), "invalid_ready"),
        (_other_protocol, "unsupported_version"),
    ],
)
def test_bad_ready_line_cleans_up_without_forwarding(carlo, adb, ready, code):
    carlo.ready = ready
    session = CarloSession(adb, carlo.binary)
    with pytest.raises(CarloError) as raised:
        session.start()
    assert raised.value.code == code
    assert TOKEN not in str(raised.value)
    assert not any("forward" in call for call in carlo.calls)
    assert carlo.calls[-1] == ["adb", "-s", SERIAL, "shell", f"rm -rf {session.session_dir}"]


def test_agent_exit_before_ready_explains_the_exit_code(carlo, adb):
    carlo.ready = lambda d: b""
    carlo.exit_code = 69
    with pytest.raises(CarloError, match="exit code 69, session directory") as raised:
        CarloSession(adb, carlo.binary).start()
    assert raised.value.code == "agent_exited"


def test_ready_line_timeout(carlo, adb):
    carlo.ready = lambda d: b'{"ready": tr'  # never finishes the line
    carlo.keep_open = True
    session = CarloSession(adb, carlo.binary, startup_timeout=0.1)
    with pytest.raises(CarloError) as raised:
        session.start()
    assert raised.value.code == "timeout"
    assert carlo.processes[0].stdout.closed


def test_session_token_and_hierarchy_never_reach_the_logs(carlo, adb, caplog):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="geppetto")
    session = CarloSession(adb, carlo.binary).start()
    session.client.hierarchy_dump()
    session.close()

    carlo.ready = lambda d: ready_line("filesystem", "/elsewhere")  # token on a bad line
    with pytest.raises(CarloError):
        CarloSession(adb, carlo.binary).start()

    assert "Carlo session started" in caplog.text
    assert TOKEN not in caplog.text
    assert "<hierarchy" not in caplog.text
    assert "Don't allow" not in caplog.text


# ── Device(backend="carlo") ──────────────────────────────────────────


@pytest.fixture
def carlo_device(carlo, tmp_path, monkeypatch) -> Iterator[Device]:
    # ``None`` in sys.modules makes any ``import uiautomator2`` fail.
    monkeypatch.setitem(sys.modules, "uiautomator2", None)
    monkeypatch.setattr("geppetto.device.time.sleep", lambda s: None)
    dev = Device(
        SERIAL,
        output_dir=tmp_path / "results",
        log_to_console=False,
        log_to_file=False,
        backend="carlo",
        carlo_binary=carlo.binary,
    )
    yield dev
    dev.close()


def test_carlo_device_never_touches_uiautomator2(carlo_device):
    assert isinstance(carlo_device.backend, CarloBackend)
    with pytest.raises(AttributeError):
        carlo_device._u2  # noqa: B018 — the property raises
    assert carlo_device.get_window_dump().find_widget(By.TEXT, "Login").id == "com.app:id/login"


def test_carlo_device_window_size_comes_from_wm_size(carlo, carlo_device):
    assert carlo_device.screen_size == (1080, 2340)
    carlo.wm_size = "Physical size: 1080x2340\nOverride size: 720x1560\n"
    assert carlo_device.screen_size == (720, 1560)
    assert ["adb", "-s", SERIAL, "shell", "wm size"] in carlo.calls


@pytest.mark.parametrize(
    ("by", "value"),
    [(By.TEXT, "Login"), (By.ID, "com.app:id/login"), (By.XPATH, "//node[@text='Login']")],
)
def test_carlo_device_await_widget_polls_the_dump(carlo, carlo_device, by, value):
    dumps = iter(["<hierarchy/>", "<hierarchy/>"])

    def appears_on_the_third_dump(rid: int) -> bytes:
        return encode_frame(HIERARCHY, rid, next(dumps, DUMP).encode())

    carlo.server.replies["hierarchy.dump"] = appears_on_the_third_dump
    assert carlo_device.await_widget(by, value, timeout=5).id == "com.app:id/login"
    assert carlo.server.commands.count("hierarchy.dump") == 3


def test_carlo_device_await_widget_times_out(carlo, carlo_device):
    carlo.server.replies["hierarchy.dump"] = hierarchy("<hierarchy/>")
    with pytest.raises(DeviceTimeoutError):
        carlo_device.await_widget(By.TEXT, "Login", timeout=0)


def test_carlo_device_refusal_raises_carlo_error(carlo, carlo_device):
    carlo.server.replies["hierarchy.dump"] = lambda rid: refused(rid, "unavailable")
    with pytest.raises(CarloError) as raised:
        carlo_device.get_window_dump()
    assert raised.value.code == "unavailable"


def test_device_context_manager_closes_the_session(carlo, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "uiautomator2", None)
    with Device(
        SERIAL,
        output_dir=tmp_path,
        log_to_console=False,
        log_to_file=False,
        backend="carlo",
        carlo_binary=carlo.binary,
    ) as dev:
        session_dir = dev.backend.session.session_dir
    assert carlo.server.commands == ["hello", "shutdown"]
    assert carlo.calls[-1] == ["adb", "-s", SERIAL, "shell", f"rm -rf {session_dir}"]
    with pytest.raises(AttributeError):
        dev.backend  # noqa: B018 — the property raises after close
    calls = len(carlo.adb_run.calls)
    dev.close()  # idempotent
    assert len(carlo.adb_run.calls) == calls


class BrokenBackend:
    def dump_hierarchy(self) -> str:
        return DUMP

    def window_size(self) -> tuple[int, int]:
        return (1, 1)

    def close(self) -> None:
        raise RuntimeError("backend broke")


def test_device_close_never_raises(adb_run, tmp_path, caplog):
    dev = Device(
        SERIAL,
        output_dir=tmp_path,
        log_to_console=False,
        log_to_file=False,
        backend=BrokenBackend(),
    )
    assert dev.screen_size == (1, 1)
    with caplog.at_level(logging.WARNING):
        dev.close()
    assert "backend broke" in caplog.text


def test_device_setup_failure_leaves_no_carlo_session(carlo, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "uiautomator2", None)
    not_a_dir = tmp_path / "file"
    not_a_dir.write_text("")
    with pytest.raises(OSError):
        Device(
            SERIAL,
            output_dir=not_a_dir,
            log_to_console=False,
            log_to_file=False,
            backend="carlo",
            carlo_binary=carlo.binary,
        )
    # The backend is created last, so no agent was pushed, started or forwarded.
    assert carlo.popen_argv == []
    assert carlo.server.commands == []
    assert not any(call[3:5] == ["forward", "tcp:0"] for call in carlo.calls)


def test_unknown_backend_name(adb_run, tmp_path):
    with pytest.raises(ValueError, match="carlo"):
        Device(SERIAL, output_dir=tmp_path, backend="appium")
    with pytest.raises(ValueError):
        create_backend("appium", AdbClient(SERIAL))


# ── doctor ───────────────────────────────────────────────────────────


def test_doctor_carlo_not_configured_is_info(monkeypatch):
    monkeypatch.delenv(BINARY_ENV, raising=False)
    check = doctor.check_carlo()
    assert (check.name, check.status) == ("carlo", Status.INFO)
    assert BINARY_ENV in check.fix


def test_doctor_carlo_ok(monkeypatch, tmp_path):
    binary = tmp_path / "carlo"
    binary.write_bytes(b"carlo")
    monkeypatch.setenv(BINARY_ENV, str(binary))
    check = doctor.check_carlo()
    assert (check.status, check.detail) == (Status.OK, str(binary))


def test_doctor_carlo_missing_file_warns(monkeypatch, tmp_path):
    monkeypatch.setenv(BINARY_ENV, str(tmp_path / "missing"))
    check = doctor.check_carlo()
    assert check.status is Status.WARN
    assert check.fix

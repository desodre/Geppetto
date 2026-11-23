"""Host side of the Carlo agent: protocol v1 framing, control client and device session.

Carlo (``carlo serve``) is a native agent pushed to the device. It prints one JSON ready line
and then serves one client over a Unix socket that the host reaches through ``adb forward``.

Frame header (16 bytes, big-endian): magic ``CRLO``, version ``1``, kind, two reserved zero
bytes, request ID (u32) and payload length (u32). Kinds: ``1`` control (UTF-8 JSON, 64 KiB),
``2`` hierarchy (raw UTF-8 XML, 8 MiB) and ``3`` video (24-byte packet header and encoder
bytes, 8 MiB). The header is validated before any payload byte is read.

The session identifier printed on the ready line is a bearer secret: it is sent in ``hello``
only and never logged. Hierarchy XML is never logged either.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import select
import socket
import struct
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple, Protocol

from ..exceptions import CarloError
from .adb import AdbClient

logger = logging.getLogger("geppetto.carlo")

MAGIC = b"CRLO"
VERSION = 1
HEADER = struct.Struct(">4sBBHII")
CONTROL, HIERARCHY, VIDEO = 1, 2, 3
CONTROL_LIMIT = 64 * 1024
BULK_LIMIT = 8 * 1024 * 1024
LIMITS = {CONTROL: CONTROL_LIMIT, HIERARCHY: BULK_LIMIT, VIDEO: BULK_LIMIT}
VIDEO_HEADER = struct.Struct(">BBHIqHHI")
CONFIG, MEDIA, END = 1, 2, 3
KEY_FRAME = 1
_U32_MAX = 0xFFFFFFFF

#: Environment variable naming the local Carlo binary to push.
BINARY_ENV = "GEPPETTO_CARLO_BINARY"
#: Parent of the per-session directory on the device.
REMOTE_ROOT = "/data/local/tmp"

JsonObject = dict[str, object]

_SESSION_RE = re.compile(r"[0-9a-f]{32}")
_ABSTRACT_RE = re.compile(r"carlo-[0-9a-f]{32}")
_READY_LIMIT = 4096
_RECV_CHUNK = 64 * 1024
#: ``carlo serve`` exit codes (sysexits) and what they mean.
_EXIT_REASONS = {64: "bad arguments", 69: "session directory or socket refused", 74: "I/O error"}
#: Seconds allowed for each short adb command of the session (mkdir, chmod, forward, rm).
_ADB_TIMEOUT = 30.0
#: Client error codes meaning the agent is gone (e.g. it exited after its idle deadline).
_RECONNECT_CODES = frozenset({"closed", "io"})


class ByteReader(Protocol):
    """Anything with a blocking ``read(size)`` that returns ``b""`` at end of stream."""

    def read(self, size: int, /) -> bytes: ...


class Frame(NamedTuple):
    """One protocol frame: its kind, request ID and payload bytes."""

    kind: int
    request_id: int
    payload: bytes


class VideoPacket(NamedTuple):
    """The decoded payload of one video-kind frame."""

    packet_type: int
    key_frame: bool
    generation: int
    pts_us: int
    width: int
    height: int
    data: bytes


# ── Framing ──────────────────────────────────────────────────────────


def encode_frame(kind: int, request_id: int, payload: bytes) -> bytes:
    """Build one frame.

    Args:
        kind: ``CONTROL``, ``HIERARCHY`` or ``VIDEO``.
        request_id: u32 request ID (``0`` when there is no request).
        payload: Payload bytes, within the kind's limit.

    Returns:
        The 16-byte header followed by *payload*.

    Raises:
        CarloError: ``unknown_kind``, ``invalid_request`` (request ID out of range) or
            ``frame_too_large``.
    """
    if kind not in LIMITS:
        raise CarloError(f"Unknown frame kind {kind}", code="unknown_kind")
    if not 0 <= request_id <= _U32_MAX:
        raise CarloError("Request ID is not a u32", code="invalid_request")
    limit = LIMITS[kind]
    if len(payload) > limit:
        raise CarloError(
            f"Frame payload of {len(payload)} bytes exceeds the limit of {limit}",
            code="frame_too_large",
        )
    return HEADER.pack(MAGIC, VERSION, kind, 0, request_id, len(payload)) + payload


def _read_up_to(stream: ByteReader, size: int) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while received < size:
        chunk = stream.read(size - received)
        if not chunk:
            break
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def read_frame(stream: ByteReader) -> Frame | None:
    """Read and validate one frame from a blocking *stream*.

    The header is checked (magic, version, reserved bytes, length against the kind's limit)
    before any payload byte is read.

    Returns:
        The frame, or ``None`` on a clean end of stream at a frame boundary.

    Raises:
        CarloError: ``truncated_frame``, ``bad_magic``, ``unsupported_version``,
            ``reserved_bits``, ``frame_too_large``, or ``unknown_kind``. Only ``unknown_kind``
            leaves the stream usable (its payload was consumed); every other code means the
            stream is desynchronised and must be closed.
    """
    header = _read_up_to(stream, HEADER.size)
    if not header:
        return None
    if len(header) < HEADER.size:
        raise CarloError(
            f"Stream ended after {len(header)} of {HEADER.size} header bytes",
            code="truncated_frame",
        )
    magic, version, kind, reserved, request_id, length = HEADER.unpack(header)
    if magic != MAGIC:
        raise CarloError("Frame magic mismatch", code="bad_magic")
    if version != VERSION:
        raise CarloError(f"Unsupported protocol version {version}", code="unsupported_version")
    if reserved:
        raise CarloError("Reserved header bytes are not zero", code="reserved_bits")
    limit = LIMITS.get(kind, BULK_LIMIT)
    if length > limit:
        raise CarloError(
            f"Frame payload of {length} bytes exceeds the limit of {limit}",
            code="frame_too_large",
        )
    payload = _read_up_to(stream, length)
    if len(payload) < length:
        raise CarloError(
            f"Stream ended after {len(payload)} of {length} payload bytes",
            code="truncated_frame",
        )
    if kind not in LIMITS:
        raise CarloError(f"Unknown frame kind {kind}", code="unknown_kind")
    return Frame(kind, request_id, payload)


def decode_video_packet(payload: bytes) -> VideoPacket:
    """Split and validate the payload of one video-kind frame.

    Returns:
        The decoded packet.

    Raises:
        CarloError: ``truncated_packet``, ``unknown_packet_type``, ``packet_reserved_bits``
            or ``invalid_packet`` (fields contradict the packet type).
    """
    if len(payload) < VIDEO_HEADER.size:
        raise CarloError(
            f"Video packet of {len(payload)} bytes is shorter than its "
            f"{VIDEO_HEADER.size}-byte header",
            code="truncated_packet",
        )
    packet_type, flags, reserved, generation, pts_us, width, height, tail = (
        VIDEO_HEADER.unpack_from(payload)
    )
    data = payload[VIDEO_HEADER.size :]
    if packet_type not in (CONFIG, MEDIA, END):
        raise CarloError(f"Unknown video packet type {packet_type}", code="unknown_packet_type")
    if flags & ~KEY_FRAME or reserved or tail:
        raise CarloError("Reserved video packet bits are not zero", code="packet_reserved_bits")
    key_frame = bool(flags & KEY_FRAME)
    if (
        generation == 0
        or (packet_type != MEDIA and (key_frame or pts_us != 0))
        or (packet_type == END) != (not data)
    ):
        raise CarloError("Video packet fields contradict its type", code="invalid_packet")
    return VideoPacket(packet_type, key_frame, generation, pts_us, width, height, data)


def encode_video_packet(packet: VideoPacket) -> bytes:
    """Build the video-kind payload for *packet* (the inverse of :func:`decode_video_packet`).

    Returns:
        The 24-byte packet header followed by ``packet.data``.

    Raises:
        CarloError: ``invalid_packet`` when a field does not fit its wire size.
    """
    flags = KEY_FRAME if packet.key_frame else 0
    try:
        header = VIDEO_HEADER.pack(
            packet.packet_type,
            flags,
            0,
            packet.generation,
            packet.pts_us,
            packet.width,
            packet.height,
            0,
        )
    except struct.error as e:
        raise CarloError(f"Video packet field out of range: {e}", code="invalid_packet") from e
    return header + packet.data


def parse_wm_size(output: str) -> tuple[int, int]:
    """Parse ``wm size`` output, preferring ``Override size`` over ``Physical size``.

    The size is the display's natural orientation (``wm size`` ignores rotation).

    Returns:
        ``(width, height)`` in pixels.

    Raises:
        CarloError: ``invalid_wm_size`` when neither size can be read from *output*.
    """
    sizes: dict[str, tuple[int, int]] = {}
    for match in re.finditer(r"(Physical|Override) size:\s*(\d+)x(\d+)", output):
        sizes[match.group(1)] = (int(match.group(2)), int(match.group(3)))
    size = sizes.get("Override") or sizes.get("Physical")
    if size is None:
        raise CarloError("Could not read the screen size from `wm size`", code="invalid_wm_size")
    return size


def parse_surface_orientation(output: str) -> int | None:
    """Read the display rotation from ``dumpsys input`` or ``dumpsys window`` output.

    Accepts ``SurfaceOrientation: <0-3>`` (``dumpsys input``) or
    ``mCurrentRotation=ROTATION_<0|90|180|270>`` (``dumpsys window``).

    Returns:
        The rotation as a quarter-turn count (``0``–``3``; ``1`` and ``3`` are landscape on a
        portrait-natural device), or ``None`` when *output* holds neither line.
    """
    match = re.search(r"SurfaceOrientation:\s*([0-3])\b", output)
    if match is not None:
        return int(match.group(1))
    match = re.search(r"mCurrentRotation=ROTATION_(0|90|180|270)\b", output)
    if match is not None:
        return int(match.group(1)) // 90
    return None


def _json_payload(payload: bytes) -> JsonObject:
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CarloError("Control frame is not JSON", code="invalid_response") from e
    if not isinstance(message, dict):
        raise CarloError("Control frame is not a JSON object", code="invalid_response")
    return message


def _error_code(message: JsonObject) -> str | None:
    error = message.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str):
            return code
    return None


# ── Control client ───────────────────────────────────────────────────


class _DeadlineReader:
    """Reads a socket without letting the whole frame take longer than one deadline."""

    def __init__(self, conn: socket.socket, deadline: float) -> None:
        self._conn = conn
        self._deadline = deadline

    def read(self, size: int, /) -> bytes:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Carlo response deadline passed")
        self._conn.settimeout(remaining)
        return self._conn.recv(min(size, _RECV_CHUNK))


class CarloControlClient:
    """Blocking request/response client for the control channel of ``carlo serve``.

    Every request (write and full response) is bounded by *timeout* seconds. Request IDs are
    assigned here and the echoed ID of each response is checked. After a timeout, transport
    error or framing violation the stream is desynchronised: every later call raises
    :class:`CarloError` with code ``closed``.

    Args:
        conn: A connected socket (the ``adb forward`` port).
        timeout: Seconds allowed for each request, from sending to the full response.
        hierarchy_timeout: Seconds allowed for ``hierarchy.dump``; longer than *timeout*
            because Carlo itself may spend over 15 s on a valid dump.
    """

    def __init__(
        self, conn: socket.socket, timeout: float = 15.0, *, hierarchy_timeout: float = 30.0
    ) -> None:
        self._conn = conn
        self._timeout = timeout
        self.hierarchy_timeout = hierarchy_timeout
        self._next_id = 1
        self._broken = False

    # ── Commands ──

    def hello(self, session_token: str) -> JsonObject:
        """Authenticate the connection with the session identifier from the ready line.

        Returns:
            The agent's hello object (agent, device, capabilities, limits).

        Raises:
            CarloError: The agent's code (``unsupported_protocol``, ``invalid_session``…), or a
                transport/protocol code.
        """
        return self._call_ok({"command": "hello", "protocol": VERSION, "session": session_token})

    def ping(self) -> None:
        """Check the agent answers.

        Raises:
            CarloError: The agent refused, or a transport/protocol code.
        """
        self._call_ok({"command": "ping"})

    def capabilities(self) -> list[JsonObject]:
        """The agent's capabilities (``name``, ``available``, ``reason``).

        Returns:
            One object per capability.

        Raises:
            CarloError: The agent refused, ``invalid_response``, or a transport/protocol code.
        """
        response = self._call_ok({"command": "capabilities"})
        items = response.get("capabilities")
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise CarloError("Malformed capabilities response", code="invalid_response")
        return [dict(i) for i in items]

    def channels(self) -> str:
        """State of the video channel.

        Returns:
            ``"pending"``, ``"attached"``, ``"absent"`` or ``"closed"``.

        Raises:
            CarloError: The agent refused, ``invalid_response``, or a transport/protocol code.
        """
        video = self._call_ok({"command": "channels"}).get("video")
        if not isinstance(video, str):
            raise CarloError("Malformed channels response", code="invalid_response")
        return video

    def hierarchy_dump(self) -> str:
        """The current UI hierarchy as XML (a kind-2 frame).

        Returns:
            The XML document, decoded from UTF-8.

        Raises:
            CarloError: The agent's code when it answers ``ok: false`` (e.g. ``unavailable``),
                ``invalid_response``, or a transport/protocol code.
        """
        frame = self._request({"command": "hierarchy.dump"}, self.hierarchy_timeout)
        if frame.kind == HIERARCHY:
            try:
                return frame.payload.decode("utf-8")
            except UnicodeDecodeError as e:
                raise CarloError("Hierarchy is not UTF-8", code="invalid_response") from e
        message = self._control_message(frame)
        self._raise_unless_ok("hierarchy.dump", message)
        raise CarloError("hierarchy.dump answered without a hierarchy", code="invalid_response")

    def video_start(
        self,
        *,
        display: int = 0,
        max_width: int = 360,
        max_height: int = 640,
        fps: int = 15,
        bitrate: int = 1_500_000,
    ) -> JsonObject:
        """Start a stream on the video channel (which must be attached).

        Returns:
            The agent's answer (``generation``, ``codec``, ``accepted`` configuration).

        Raises:
            CarloError: The agent's code (``video_channel_absent``, ``unavailable``…), or a
                transport/protocol code.
        """
        return self._call_ok(
            {
                "command": "video.start",
                "display": display,
                "max_width": max_width,
                "max_height": max_height,
                "fps": fps,
                "bitrate": bitrate,
                "encoder": "default",
            }
        )

    def video_stop(self) -> JsonObject:
        """Stop the running stream, or collect the report of one that ended by itself.

        Returns:
            The stop report (``generation``, ``reason``, ``packets``, ``bytes``, ``key_frames``).

        Raises:
            CarloError: The agent's code (``not_streaming``, ``timeout``…), or a
                transport/protocol code.
        """
        return self._call_ok({"command": "video.stop"})

    def shutdown(self) -> None:
        """Ask the agent to end the session and exit.

        Raises:
            CarloError: The agent refused, or a transport/protocol code.
        """
        self._call_ok({"command": "shutdown"})
        self._broken = True  # the agent closes the connection after answering

    def close(self) -> None:
        """Close the connection (the agent then ends the session). Never raises."""
        self._broken = True
        try:
            self._conn.close()
        except OSError:
            pass

    # ── Transport ──

    def _call_ok(self, message: JsonObject) -> JsonObject:
        response = self._control_message(self._request(message))
        self._raise_unless_ok(str(message["command"]), response)
        return response

    @staticmethod
    def _raise_unless_ok(command: str, response: JsonObject) -> None:
        if response.get("ok") is True:
            return
        code = _error_code(response) or "invalid_response"
        raise CarloError(f"Carlo refused {command}: {code}", code=code)

    @staticmethod
    def _control_message(frame: Frame) -> JsonObject:
        if frame.kind != CONTROL:
            raise CarloError(
                f"Unexpected frame kind {frame.kind} on the control channel",
                code="unexpected_kind",
            )
        return _json_payload(frame.payload)

    def _request(self, message: JsonObject, timeout: float | None = None) -> Frame:
        if self._broken:
            raise CarloError("The Carlo control connection is closed", code="closed")
        limit = self._timeout if timeout is None else timeout
        request_id = self._next_id
        self._next_id = request_id % _U32_MAX + 1
        body = json.dumps(message, separators=(",", ":")).encode()
        data = encode_frame(CONTROL, request_id, body)
        deadline = time.monotonic() + limit
        try:
            self._conn.settimeout(limit)
            self._conn.sendall(data)
            frame = self._receive(deadline)
        except TimeoutError as e:
            self._broken = True
            raise CarloError(f"Carlo did not answer within {limit}s", code="timeout") from e
        except OSError as e:
            self._broken = True
            raise CarloError(f"Carlo control connection failed: {e}", code="io") from e
        if frame.kind == CONTROL:
            rejection = _json_payload(frame.payload)
            if "ok" not in rejection and _error_code(rejection) is not None:
                # A framing rejection: the agent closes the stream after sending it.
                self._broken = True
                self._raise_unless_ok(str(message["command"]), rejection)
        if frame.request_id != request_id:
            self._broken = True
            raise CarloError("Response does not echo the request ID", code="invalid_response")
        return frame

    def _receive(self, deadline: float) -> Frame:
        reader = _DeadlineReader(self._conn, deadline)
        while True:
            try:
                frame = read_frame(reader)
            except CarloError as e:
                if e.code == "unknown_kind":
                    continue  # recoverable: the payload was consumed
                self._broken = True
                raise
            if frame is None:
                self._broken = True
                raise CarloError("Carlo closed the control connection", code="closed")
            return frame


# ── Device session ───────────────────────────────────────────────────


@contextmanager
def _adb_step(what: str) -> Iterator[None]:
    try:
        yield
    except subprocess.TimeoutExpired as e:
        raise CarloError(f"adb timed out trying to {what}", code="timeout") from e
    except (subprocess.CalledProcessError, OSError) as e:
        raise CarloError(f"adb failed to {what}", code="adb") from e


def _resolve_binary(binary: str | Path | None) -> Path:
    raw = binary if binary is not None else os.environ.get(BINARY_ENV)
    if not raw:
        raise CarloError(
            f"No Carlo binary: pass carlo_binary or set {BINARY_ENV}", code="binary_missing"
        )
    path = Path(raw)
    if not path.is_file():
        raise CarloError(f"Carlo binary not found: {path}", code="binary_missing")
    return path


def _verify_sha256(path: Path, expected: str) -> None:
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if not hmac.compare_digest(digest, expected.strip().lower()):
        raise CarloError(f"SHA-256 of {path} does not match", code="checksum_mismatch")


def _stop_process(process: subprocess.Popen[str]) -> None:
    """Let the local ``adb shell`` end by itself, else terminate/kill it; bounded, never raises."""
    for stop in (None, process.terminate, process.kill):
        if stop is not None:
            try:
                stop()
            except OSError:
                pass
        try:
            process.wait(timeout=2 if stop is None else 5)
            break
        except subprocess.TimeoutExpired:
            continue
    else:
        logger.warning("The local adb process of Carlo (pid %d) did not exit", process.pid)
    if process.stdout is not None:
        process.stdout.close()


class _Ready(NamedTuple):
    transport: str
    socket_name: str
    session: str


class CarloSession:
    """One running ``carlo serve`` on a device, reachable through an authenticated client.

    :meth:`start` creates a private ``0700`` directory under ``/data/local/tmp``, pushes the
    binary into it, starts the agent, reads its ready line, forwards its socket with
    ``adb forward tcp:0`` and authenticates with ``hello``. Any failure undoes what was done;
    :meth:`close` ends the session and removes the forward, the process and the directory.
    Usable as a context manager.

    Carlo exits by itself after an idle deadline (30 s without a client request). With
    *auto_reconnect*, :meth:`dump_hierarchy` then cleans the old session up and starts a fresh
    one (in a new directory) once before retrying.

    Args:
        adb: Transport of the target device.
        binary: Local Carlo binary for the device's ABI; defaults to ``$GEPPETTO_CARLO_BINARY``.
        sha256: Expected SHA-256 (hex) of *binary*, checked before pushing it.
        startup_timeout: Seconds allowed for the ready line and for connecting.
        request_timeout: Seconds allowed for each control request.
        hierarchy_timeout: Seconds allowed for ``hierarchy.dump``.
        auto_reconnect: Restart the session once when :meth:`dump_hierarchy` finds the
            connection ``closed`` or failing with ``io``.
    """

    def __init__(
        self,
        adb: AdbClient,
        binary: str | Path | None = None,
        *,
        sha256: str | None = None,
        startup_timeout: float = 15.0,
        request_timeout: float = 15.0,
        hierarchy_timeout: float = 30.0,
        auto_reconnect: bool = True,
    ) -> None:
        self.adb = adb
        self._binary_arg = binary
        self._sha256 = sha256
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self.hierarchy_timeout = hierarchy_timeout
        self.auto_reconnect = auto_reconnect
        self.session_dir = ""
        self.remote_binary = ""
        self._new_session_dir()
        self.port: int | None = None
        self.hello_info: JsonObject = {}
        self._dir_created = False
        self._process: subprocess.Popen[str] | None = None
        self._client: CarloControlClient | None = None

    @property
    def client(self) -> CarloControlClient:
        """The authenticated control client.

        Raises:
            CarloError: ``not_started`` before :meth:`start` or after :meth:`close`.
        """
        if self._client is None:
            raise CarloError("The Carlo session is not running", code="not_started")
        return self._client

    def start(self) -> CarloSession:
        """Push, start and connect to the agent.

        Returns:
            This session, started.

        Raises:
            CarloError: ``binary_missing``, ``checksum_mismatch``, ``adb``, ``timeout``,
                ``agent_exited``, ``invalid_ready``, ``io``, the agent's ``hello`` refusal, or
                ``already_started``. Everything already set up is cleaned up first.
        """
        if self._process is not None or self._client is not None:
            raise CarloError("The Carlo session was already started", code="already_started")
        self._launch()
        return self

    def dump_hierarchy(self) -> str:
        """The current UI hierarchy, restarting the session once if Carlo went away.

        Returns:
            The hierarchy XML sent by Carlo.

        Raises:
            CarloError: ``not_started`` before :meth:`start` or after :meth:`close`; the
                agent's refusal (``unavailable``, ``conflict``, ``truncated``…) or ``timeout``,
                never retried; ``closed``/``io`` when *auto_reconnect* is off or the retry fails
                too; any :meth:`start` code when the restart fails (the session is then cleaned
                up and :meth:`close` has nothing left to do).
        """
        try:
            return self.client.hierarchy_dump()
        except CarloError as e:
            if not self.auto_reconnect or e.code not in _RECONNECT_CODES:
                raise
            logger.debug("Carlo connection lost (%s); restarting the session once", e.code)
        self._cleanup()
        self._new_session_dir()  # mkdir must not collide with a directory left behind
        self._launch()
        return self.client.hierarchy_dump()

    def _new_session_dir(self) -> None:
        self.session_dir = f"{REMOTE_ROOT}/geppetto-carlo-{secrets.token_hex(8)}"
        self.remote_binary = f"{self.session_dir}/carlo"

    def _launch(self) -> None:
        binary = _resolve_binary(self._binary_arg)
        if self._sha256 is not None:
            _verify_sha256(binary, self._sha256)
        try:
            self._start(binary)
        except BaseException:
            self._cleanup()
            raise

    def _start(self, binary: Path) -> None:
        adb = self.adb
        with _adb_step("create the Carlo session directory"):
            adb.shell(["mkdir", "-m", "700", self.session_dir], timeout=_ADB_TIMEOUT)
        self._dir_created = True
        with _adb_step("push the Carlo binary"):
            adb.push(binary, self.remote_binary)
            adb.shell(["chmod", "700", self.remote_binary], timeout=_ADB_TIMEOUT)
        with _adb_step("start Carlo"):
            self._process = adb.stream_shell(
                [self.remote_binary, "serve", "--session-dir", self.session_dir]
            )
        deadline = time.monotonic() + self.startup_timeout
        ready = self._parse_ready(self._read_ready_line(self._process, deadline))
        kind = "localfilesystem" if ready.transport == "filesystem" else "localabstract"
        with _adb_step("forward the Carlo socket"):
            out = adb.cmd(["forward", "tcp:0", f"{kind}:{ready.socket_name}"], timeout=_ADB_TIMEOUT)
        try:
            self.port = int(out.strip().splitlines()[-1])
        except (ValueError, IndexError) as e:
            raise CarloError("adb forward did not report a port", code="adb") from e
        remaining = max(deadline - time.monotonic(), 0.1)
        try:
            conn = socket.create_connection(("127.0.0.1", self.port), timeout=remaining)
        except OSError as e:
            raise CarloError(f"Could not connect to Carlo: {e}", code="io") from e
        self._client = CarloControlClient(
            conn, timeout=self.request_timeout, hierarchy_timeout=self.hierarchy_timeout
        )
        self.hello_info = self._client.hello(ready.session)
        logger.info("Carlo session started on %s (%s transport)", adb.serial, ready.transport)

    def _read_ready_line(self, process: subprocess.Popen[str], deadline: float) -> bytes:
        stdout = process.stdout
        if stdout is None:
            raise CarloError("Carlo stdout is not readable", code="agent_exited")
        fd = stdout.fileno()
        data = bytearray()
        while b"\n" not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CarloError(
                    f"Carlo was not ready within {self.startup_timeout}s", code="timeout"
                )
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                continue
            chunk = os.read(fd, _READY_LIMIT)
            if not chunk:
                try:
                    code = process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    code = None
                reason = _EXIT_REASONS.get(code, "") if code is not None else ""
                raise CarloError(
                    f"Carlo exited before it was ready (exit code {code}"
                    f"{', ' + reason if reason else ''})",
                    code="agent_exited",
                )
            data += chunk
            if len(data) > _READY_LIMIT:
                raise CarloError("Carlo ready line is too long", code="invalid_ready")
        return bytes(data.split(b"\n", 1)[0])

    def _parse_ready(self, line: bytes) -> _Ready:
        # The line holds the session secret: errors describe fields, never the content.
        try:
            ready = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise CarloError("Carlo ready line is not JSON", code="invalid_ready") from e
        if not isinstance(ready, dict) or ready.get("ready") is not True:
            raise CarloError("Carlo ready line is malformed", code="invalid_ready")
        if ready.get("protocol") != VERSION:
            raise CarloError("Carlo speaks another protocol version", code="unsupported_version")
        transport = ready.get("transport")
        name = ready.get("socket")
        session = ready.get("session")
        if not isinstance(session, str) or not _SESSION_RE.fullmatch(session):
            raise CarloError("Carlo ready line has no valid session", code="invalid_ready")
        if transport == "filesystem":
            valid = name == f"{self.session_dir}/control.sock"
        elif transport == "abstract":
            valid = isinstance(name, str) and _ABSTRACT_RE.fullmatch(name) is not None
        else:
            valid = False
        if not valid or not isinstance(name, str) or not isinstance(transport, str):
            raise CarloError("Carlo ready line has an invalid socket", code="invalid_ready")
        return _Ready(transport, name, session)

    def close(self) -> None:
        """End the session: ``shutdown``, then remove the forward, the process and the
        directory. Idempotent; cleanup failures are logged, never raised."""
        client, self._client = self._client, None
        if client is not None:
            try:
                client.shutdown()
            except CarloError as e:
                logger.debug("Carlo shutdown failed (%s); closing anyway", e.code)
            client.close()
        self._cleanup()

    def _cleanup(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        if self.port is not None:
            port, self.port = self.port, None
            try:
                self.adb.cmd(["forward", "--remove", f"tcp:{port}"], timeout=_ADB_TIMEOUT)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
                logger.warning("Could not remove the Carlo forward tcp:%d: %s", port, e)
        process, self._process = self._process, None
        if process is not None:
            _stop_process(process)
        if self._dir_created:
            self._dir_created = False
            try:
                self.adb.shell(["rm", "-rf", self.session_dir], timeout=_ADB_TIMEOUT)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
                logger.warning("Could not remove %s: %s", self.session_dir, e)

    def __enter__(self) -> CarloSession:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

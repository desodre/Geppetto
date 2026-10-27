"""Logcat as a live stream: filters, a ring buffer and waiting for (or forbidding) a line.

::

    with device.logcat(package="com.example", level="I") as log:
        device.click(...)
        log.expect("Payment OK", timeout=10)
        log.expect_no("Exception", within=2)

The stream starts at the device's current time (``logcat -T``): it never clears the log
buffers and never replays old lines.
"""

from __future__ import annotations

import collections
import re
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING

from .exceptions import LogNotFoundError

if TYPE_CHECKING:
    from .core.adb import AdbClient

LEVELS = "VDIWEF"

# 10-27 14:03:11.123  1234  1250 E AndroidRuntime: FATAL EXCEPTION: main
_THREADTIME = re.compile(
    r"^(?P<date>\d\d-\d\d)\s+(?P<time>\d\d:\d\d:\d\d\.\d+)\s+(?P<pid>\d+)\s+(?P<tid>\d+)\s+"
    r"(?P<level>[VDIWEFA])\s+(?P<tag>.*?)\s*:\s?(?P<message>.*)$"
)


@dataclass(frozen=True)
class LogLine:
    """One logcat line (``-v threadtime``)."""

    date: str
    time: str
    pid: int
    tid: int
    level: str
    tag: str
    message: str
    #: ``time.monotonic()`` on the host when the line was read.
    received: float = 0.0

    @classmethod
    def parse(cls, raw: str, received: float = 0.0) -> LogLine | None:
        """``None`` for lines that are not log entries (``--------- beginning of main``)."""
        m = _THREADTIME.match(raw.rstrip("\n"))
        if m is None:
            return None
        return cls(
            m["date"],
            m["time"],
            int(m["pid"]),
            int(m["tid"]),
            m["level"],
            m["tag"],
            m["message"],
            received,
        )

    def __str__(self) -> str:
        cabeca = f"{self.date} {self.time} {self.pid:5} {self.tid:5} {self.level}"
        return f"{cabeca} {self.tag}: {self.message}"


def _level_index(level: str) -> int:
    return LEVELS.index("F" if level == "A" else level)


class LogcatStream:
    """Reads ``logcat`` in a background thread and keeps the matching lines.

    Filters (all optional, combined with AND): *package* (lines from the app's processes, followed
    across restarts), *tags*, minimum *level* (``V D I W E F``) and a *pattern* regex on the
    message. *keep_seconds* bounds the buffer (also *max_lines*).
    """

    #: How often the pids of *package* are refreshed (the app may restart).
    PID_REFRESH = 2.0

    def __init__(
        self,
        adb: AdbClient,
        *,
        package: str | None = None,
        tags: list[str] | None = None,
        level: str = "V",
        pattern: str | None = None,
        keep_seconds: float = 120,
        max_lines: int = 20_000,
    ) -> None:
        if level not in LEVELS:
            raise ValueError(f"level must be one of {', '.join(LEVELS)}")
        self._adb = adb
        self.package = package
        self.tags = set(tags or ())
        self.level = level
        self.pattern = re.compile(pattern) if pattern else None
        self.keep_seconds = keep_seconds
        self._lines: collections.deque[LogLine] = collections.deque(maxlen=max_lines)
        self._cond = threading.Condition()
        self._pids: set[int] = set()
        self._pids_at = 0.0
        self._listeners: list[Callable[[LogLine], None]] = []
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._last_read = time.monotonic()

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> LogcatStream:
        agora = self._adb.shell(["date", "+%m-%d %H:%M:%S.000"]).strip()
        args = ["logcat", "-v", "threadtime"] + (["-T", agora] if agora else ["-T", "1"])
        self._process = self._adb.stream_shell(args)
        self._thread = threading.Thread(target=self._read, name="geppetto-logcat", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> LogcatStream:
        return self.start() if self._process is None else self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    # ── reading ──────────────────────────────────────────────────────

    def add_listener(self, callback: Callable[[LogLine], None]) -> None:
        """Call *callback* for every line read, before filtering (crash detection uses it)."""
        self._listeners.append(callback)

    def _read(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw in process.stdout:
            self._last_read = time.monotonic()
            line = LogLine.parse(raw, self._last_read)
            if line is None:
                continue
            for callback in self._listeners:
                callback(line)
            if self._accepts(line):
                with self._cond:
                    self._lines.append(line)
                    self._cond.notify_all()

    def _package_pids(self) -> set[int]:
        if self.package is None:
            return set()
        if time.monotonic() - self._pids_at > self.PID_REFRESH:
            try:
                saida = self._adb.shell(["pidof", self.package])
                self._pids = {int(p) for p in saida.split() if p.isdigit()}
            except subprocess.CalledProcessError:
                self._pids = set()  # pidof exits 1 when the app is not running
            self._pids_at = time.monotonic()
        return self._pids

    def _accepts(self, line: LogLine) -> bool:
        if _level_index(line.level) < _level_index(self.level):
            return False
        if self.tags and line.tag not in self.tags:
            return False
        if self.pattern is not None and not self.pattern.search(line.message):
            return False
        return self.package is None or line.pid in self._package_pids()

    def settle(self, quiet: float = 0.3, timeout: float = 2.0) -> None:
        """Wait until no line arrived for *quiet* seconds (at most *timeout*).

        Lets lines the device already wrote reach the reader before deciding (e.g. a crash at the
        end of a test)."""
        fim = time.monotonic() + timeout
        while time.monotonic() < fim and time.monotonic() - self._last_read < quiet:
            time.sleep(0.05)

    def lines(self, last_seconds: float | None = None) -> list[LogLine]:
        """The kept lines, oldest first (only the last *last_seconds* when given)."""
        limite = time.monotonic() - (
            last_seconds if last_seconds is not None else self.keep_seconds
        )
        with self._cond:
            while self._lines and self._lines[0].received < time.monotonic() - self.keep_seconds:
                self._lines.popleft()
            return [line for line in self._lines if line.received >= limite]

    def text(self, last_seconds: float | None = None) -> str:
        return "\n".join(map(str, self.lines(last_seconds)))

    def __iter__(self) -> Iterator[LogLine]:
        return iter(self.lines())

    # ── assertions ───────────────────────────────────────────────────

    def _match(self, pattern: str | re.Pattern[str], desde: int) -> LogLine | None:
        regex = re.compile(pattern) if isinstance(pattern, str) else pattern
        for line in list(self._lines)[desde:]:
            if regex.search(line.message) or regex.search(str(line)):
                return line
        return None

    def expect(
        self, pattern: str | re.Pattern[str], timeout: float = 10, *, since_start: bool = False
    ) -> LogLine:
        """Wait for a line matching *pattern* (regex on the message or the whole line).

        Only lines that arrive from now on count, unless *since_start*. Raises
        :class:`LogNotFoundError` with the last lines read when it times out.
        """
        with self._cond:
            desde = 0 if since_start else len(self._lines)
            fim = time.monotonic() + timeout
            while True:
                achada = self._match(pattern, desde)
                if achada is not None:
                    return achada
                restante = fim - time.monotonic()
                if restante <= 0:
                    break
                self._cond.wait(restante)
        ultimas = "\n".join(map(str, list(self._lines)[-15:])) or "(no lines)"
        raise LogNotFoundError(
            f"No log line matching {pattern!r} within {timeout}s. Last lines:\n{ultimas}"
        )

    def expect_no(self, pattern: str | re.Pattern[str], within: float = 2) -> None:
        """Watch for *within* seconds and fail if a line matching *pattern* shows up."""
        with self._cond:
            desde = len(self._lines)
        time.sleep(within)
        with self._cond:
            achada = self._match(pattern, desde)
        if achada is not None:
            raise LogNotFoundError(f"Unexpected log line matching {pattern!r}:\n{achada}")


def expect_log(stream: LogcatStream, pattern: str, timeout: float = 10) -> LogLine:
    """Functional form of :meth:`LogcatStream.expect`."""
    return stream.expect(pattern, timeout)


def expect_no_log(stream: LogcatStream, pattern: str, within: float = 2) -> None:
    """Functional form of :meth:`LogcatStream.expect_no`."""
    stream.expect_no(pattern, within)

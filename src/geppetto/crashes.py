"""Detect app crashes in logcat while code runs: Java exceptions, ANRs and native signals.

::

    with device.watch_crashes("com.example"):
        device.click(...)          # raises AppCrashedError at the end if the app crashed

The watcher listens to every logcat line (before the stream's filters), so it also sees the
crash of an app that is not the one being filtered.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from types import TracebackType

from .exceptions import AppCrashedError
from .logcat import LogcatStream, LogLine

_PROCESS = re.compile(r"Process: (?P<process>[^,\s]+), PID: (?P<pid>\d+)")
_ANR = re.compile(r"ANR in (?P<process>\S+)")
_SIGNAL = re.compile(
    r"Fatal signal \d+ \((?P<signal>\w+)\).*?pid (?P<pid>\d+) \((?P<process>[^)]+)\)"
)
_TOMBSTONE = re.compile(r"Tombstone written to: (?P<path>\S+)")
_DETAIL_LIMIT = 200


@dataclass
class Crash:
    """One crash: ``kind`` is ``java``, ``anr`` or ``native``."""

    kind: str
    process: str
    pid: int
    summary: str
    details: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        cabeca = (
            f"{self.kind.upper()} crash in {self.process or '?'} (pid {self.pid}): {self.summary}"
        )
        return "\n".join([cabeca, *self.details])


class CrashWatcher:
    """Collects crashes from a :class:`LogcatStream`; *packages* limits them to those processes
    (a process name like ``com.example:remote`` counts for ``com.example``)."""

    def __init__(self, stream: LogcatStream, packages: list[str] | tuple[str, ...] = ()) -> None:
        self.stream = stream
        self.packages = tuple(packages)
        self._crashes: list[Crash] = []
        self._open: Crash | None = None  # crash whose details are still being read
        self._lock = threading.Lock()
        self._started_stream = False
        stream.add_listener(self._on_line)

    # ── parsing ──────────────────────────────────────────────────────

    def _on_line(self, line: LogLine) -> None:
        with self._lock:
            novo = self._new_crash(line)
            if novo is not None:
                self._open = novo
                self._crashes.append(novo)
                return
            aberto = self._open
            if aberto is None:
                return
            if self._continues(aberto, line) and len(aberto.details) < _DETAIL_LIMIT:
                aberto.details.append(line.message)
                if aberto.kind == "java" and not aberto.process:
                    m = _PROCESS.search(line.message)
                    if m:
                        aberto.process, aberto.pid = m["process"], int(m["pid"])
                tombstone = _TOMBSTONE.search(line.message)
                if tombstone:
                    aberto.details.append(f"tombstone: {tombstone['path']}")
            elif line.pid == aberto.pid or line.tag == "AndroidRuntime":
                self._open = None

    @staticmethod
    def _new_crash(line: LogLine) -> Crash | None:
        if line.tag == "AndroidRuntime" and line.message.startswith("FATAL EXCEPTION"):
            return Crash("java", "", line.pid, line.message)
        if line.tag == "ActivityManager" and line.level == "E":
            m = _ANR.match(line.message)
            if m:
                return Crash("anr", m["process"], line.pid, line.message)
        m = _SIGNAL.search(line.message)
        if m:
            return Crash("native", m["process"], int(m["pid"]), f"{m['signal']}: {line.message}")
        return None

    @staticmethod
    def _continues(crash: Crash, line: LogLine) -> bool:
        if crash.kind == "java":
            return line.tag == "AndroidRuntime" and line.level == "E"
        if crash.kind == "anr":
            return line.tag == "ActivityManager" and line.level == "E"
        return line.tag in ("DEBUG", "tombstoned", "crash_dump64", "crash_dump32")

    # ── results ──────────────────────────────────────────────────────

    def _watched(self, crash: Crash) -> bool:
        if not self.packages:
            return True
        return any(crash.process == p or crash.process.startswith(p + ":") for p in self.packages)

    def crashes(self, settle: bool = True) -> list[Crash]:
        """The crashes seen so far; with *settle*, first waits briefly for lines already written."""
        if settle:
            self.stream.settle()
        with self._lock:
            return [c for c in self._crashes if self._watched(c)]

    def raise_if_crashed(self) -> None:
        """Raise :class:`AppCrashedError` with every crash seen (first one's stack included)."""
        crashes = self.crashes()
        if crashes:
            raise AppCrashedError("\n\n".join(map(str, crashes)))

    # ── context manager ──────────────────────────────────────────────

    def __enter__(self) -> CrashWatcher:
        if not self.stream.running:
            self.stream.start()
            self._started_stream = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                self.raise_if_crashed()
        finally:
            if self._started_stream:
                self.stream.stop()

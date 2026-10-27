import threading
import time

import pytest

from geppetto import AppCrashedError, LogLine, LogNotFoundError
from geppetto.crashes import CrashWatcher
from geppetto.logcat import LogcatStream

# Real-looking threadtime output: a Java crash (as `am crash` produces), an ANR and a native crash.
JAVA = """\
--------- beginning of crash
10-27 21:10:01.100  4321  4321 I SettingsActivity: onResume
10-27 21:10:02.200  4321  4321 E AndroidRuntime: FATAL EXCEPTION: main
10-27 21:10:02.201  4321  4321 E AndroidRuntime: Process: com.android.settings, PID: 4321
10-27 21:10:02.202  4321  4321 E AndroidRuntime: android.app.RemoteServiceException$CrashedByAdbException: shell-induced crash
10-27 21:10:02.203  4321  4321 E AndroidRuntime: \tat android.app.ActivityThread.throwRemoteServiceException(ActivityThread.java:2009)
10-27 21:10:02.300   600  700 I ActivityManager: Process com.android.settings (pid 4321) has died
"""
ANR = """\
10-27 21:11:00.000   600   650 E ActivityManager: ANR in com.example.app (com.example.app/.MainActivity)
10-27 21:11:00.001   600   650 E ActivityManager: PID: 5555
10-27 21:11:00.002   600   650 E ActivityManager: Reason: Input dispatching timed out
"""
NATIVE = """\
10-27 21:12:00.000  7777  7790 F libc    : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0 in tid 7790 (RenderThread), pid 7777 (com.example.game)
10-27 21:12:00.100  7800  7800 F DEBUG   : *** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
10-27 21:12:00.101  7800  7800 F DEBUG   : backtrace:
10-27 21:12:00.102  7800  7800 F DEBUG   :       #00 pc 0000000000012345  /system/lib64/libgame.so
10-27 21:12:00.200   500   500 E tombstoned: Tombstone written to: /data/tombstones/tombstone_07
"""


class FakeProcess:
    def __init__(self, text: str, delay: float = 0.0):
        self.text, self.delay, self._done = text, delay, False
        self.stdout = self._lines()

    def _lines(self):
        for line in self.text.splitlines(keepends=True):
            if self.delay:
                time.sleep(self.delay)
            yield line
        self._done = True

    def poll(self):
        return 0 if self._done else None

    def terminate(self):
        self._done = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


class FakeAdb:
    def __init__(self, text: str, delay: float = 0.0, pids: str = ""):
        self.text, self.delay, self.pids, self.commands = text, delay, pids, []

    def shell(self, command):
        self.commands.append(command)
        if command[0] == "date":
            return "10-27 21:10:00.000\n"
        if command[0] == "pidof":
            return self.pids
        return ""

    def stream_shell(self, command):
        self.commands.append(command)
        return FakeProcess(self.text, self.delay)


def run(stream: LogcatStream) -> LogcatStream:
    stream.start()
    stream._thread.join(timeout=5)
    return stream


def test_parse_threadtime():
    line = LogLine.parse("10-27 21:10:02.200  4321  4322 E AndroidRuntime: FATAL EXCEPTION: main")
    assert (line.pid, line.tid, line.level, line.tag, line.message) == (
        4321,
        4322,
        "E",
        "AndroidRuntime",
        "FATAL EXCEPTION: main",
    )
    assert LogLine.parse("--------- beginning of crash") is None


def test_stream_starts_at_the_device_time_without_clearing():
    adb = FakeAdb("")
    run(LogcatStream(adb))
    assert ["logcat", "-v", "threadtime", "-T", "10-27 21:10:00.000"] in adb.commands
    assert "logcat -c" not in adb.commands


def test_filters_by_level_tag_pattern_and_package():
    texto = JAVA + ANR
    assert [linha.tag for linha in run(LogcatStream(FakeAdb(texto), level="E")).lines()] == [
        "AndroidRuntime"
    ] * 4 + ["ActivityManager"] * 3
    assert len(run(LogcatStream(FakeAdb(texto), tags=["SettingsActivity"])).lines()) == 1
    assert len(run(LogcatStream(FakeAdb(texto), pattern=r"^Reason:")).lines()) == 1
    so_settings = run(LogcatStream(FakeAdb(texto, pids="4321\n"), package="com.android.settings"))
    assert {linha.pid for linha in so_settings.lines()} == {4321}


def test_expect_waits_for_a_future_line():
    stream = LogcatStream(FakeAdb(JAVA + ANR, delay=0.02)).start()
    assert stream.expect(r"ANR in com\.example\.app", timeout=3).pid == 600
    stream.stop()


def test_expect_times_out_with_the_last_lines():
    stream = run(LogcatStream(FakeAdb(JAVA)))
    with pytest.raises(LogNotFoundError, match="FATAL EXCEPTION"):
        stream.expect("Payment OK", timeout=0.1, since_start=True)


def test_expect_no_fails_when_the_line_shows_up():
    stream = LogcatStream(FakeAdb(JAVA, delay=0.05)).start()
    with pytest.raises(LogNotFoundError, match="Unexpected"):
        stream.expect_no("FATAL", within=1)
    stream.stop()


@pytest.mark.parametrize(
    ("texto", "kind", "process", "trecho"),
    [
        (JAVA, "java", "com.android.settings", "CrashedByAdbException"),
        (ANR, "anr", "com.example.app", "Input dispatching timed out"),
        (NATIVE, "native", "com.example.game", "tombstone: /data/tombstones/tombstone_07"),
    ],
)
def test_crash_kinds(texto, kind, process, trecho):
    stream = LogcatStream(FakeAdb(texto))
    watcher = CrashWatcher(stream)
    run(stream)
    [crash] = watcher.crashes(settle=False)
    assert (crash.kind, crash.process) == (kind, process)
    assert trecho in str(crash)


def test_watch_only_the_given_packages():
    stream = LogcatStream(FakeAdb(JAVA + ANR + NATIVE))
    watcher = CrashWatcher(stream, ["com.example.app"])
    run(stream)
    assert [c.kind for c in watcher.crashes(settle=False)] == ["anr"]


def test_context_manager_raises_with_the_stack():
    stream = LogcatStream(FakeAdb(JAVA))
    with pytest.raises(AppCrashedError, match="CrashedByAdbException"):
        with CrashWatcher(stream, ["com.android.settings"]):
            stream._thread.join(timeout=5)


def test_no_crash_no_error():
    stream = LogcatStream(FakeAdb("10-27 21:10:01.100  4321  4321 I App: ok\n"))
    with CrashWatcher(stream):
        stream._thread.join(timeout=5)


def test_stream_is_thread_safe_for_readers():
    stream = LogcatStream(FakeAdb(JAVA * 50, delay=0.0005)).start()
    erros = []

    def ler():
        try:
            for _ in range(50):
                stream.lines()
        except Exception as e:  # noqa: BLE001
            erros.append(e)

    threads = [threading.Thread(target=ler) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stream.stop()
    assert erros == []

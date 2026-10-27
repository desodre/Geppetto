from geppetto.core import adb as adb_module
from geppetto.recording import MAX_SECONDS, ScreenRecording


class FakeProcess:
    def __init__(self):
        self.running = True

    def poll(self):
        return None if self.running else 0

    def wait(self, timeout=None):
        self.running = False
        return 0


def test_recording_stops_with_sigint_and_pulls(adb, adb_run, monkeypatch, tmp_path):
    processo = FakeProcess()
    lancados = []
    monkeypatch.setattr(
        adb_module.subprocess, "Popen", lambda argv, **k: lancados.append(argv) or processo
    )
    monkeypatch.setattr("geppetto.recording.time.sleep", lambda s: None)

    gravacao = ScreenRecording(adb, "teste", time_limit=999).start()
    assert gravacao.time_limit == MAX_SECONDS
    assert lancados[-1][-1] == "screenrecord --time-limit 180 /sdcard/DCIM/Geppetto/teste.mp4"
    assert gravacao.running

    local = gravacao.stop(tmp_path / "video.mp4")

    assert local == str(tmp_path / "video.mp4")
    assert "pkill -INT screenrecord" in adb_run.shell_lines()
    assert adb_run.shell_lines()[-1] == "rm /sdcard/DCIM/Geppetto/teste.mp4"
    assert not gravacao.running

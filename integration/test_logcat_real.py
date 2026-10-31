"""Logcat streaming and crash detection against a real device (Android 13+ for `am crash`)."""

import time

import pytest

from geppetto import AppCrashedError, Device
from geppetto.core.adb import AdbClient

SETTINGS = "com.android.settings"


@pytest.fixture(scope="module")
def dev(serial, tmp_path_factory):
    return Device(serial, output_dir=tmp_path_factory.mktemp("results"), log_to_console=False)


def _sdk(serial) -> int:
    return int(AdbClient(serial).shell("getprop ro.build.version.sdk").strip() or 0)


def test_expect_a_line_written_after_the_start(dev):
    with dev.logcat(tags=["GeppettoIT"]) as log:
        dev.adb.shell(["log", "-t", "GeppettoIT", "payment ok 42"])
        linha = log.expect(r"payment ok \d+", timeout=15)
    assert linha.tag == "GeppettoIT"


def test_forced_crash_is_detected_with_the_exception(dev, serial):
    if _sdk(serial) < 33:
        pytest.skip("`am crash` needs Android 13+")
    dev.open_app(SETTINGS)
    assert dev.await_for_activity(SETTINGS, timeout=20)
    with pytest.raises(AppCrashedError, match="FATAL EXCEPTION|CrashedByAdbException"):
        with dev.watch_crashes(SETTINGS):
            dev.adb.shell(["am", "crash", SETTINGS])
            time.sleep(3)  # the watcher also settles on exit, but give the crash time to happen


def test_plugin_fails_a_passing_test_when_the_app_crashes(pytester, serial, tmp_path):
    if _sdk(serial) < 33:
        pytest.skip("`am crash` needs Android 13+")
    pytester.makepyfile(
        f"""
        import time

        def test_passa_mas_o_app_cai(device):
            device.open_app("{SETTINGS}")
            assert device.await_for_activity("{SETTINGS}", timeout=20)
            device.adb.shell(["am", "crash", "{SETTINGS}"])
            time.sleep(3)
        """
    )
    result = pytester.runpytest(
        "--serial",
        serial,
        "--geppetto-watch",
        SETTINGS,
        "--geppetto-output",
        str(tmp_path),
        "--geppetto-artifacts=on-failure",
    )
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*App crashed during the test*"])

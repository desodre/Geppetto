"""AdbClient against a real device: quoting reaches the device shell intact."""

from geppetto.core.adb import AdbClient, wait_for_boot


def test_arguments_reach_the_device_literally(serial):
    adb = AdbClient(serial)
    # Without quoting, the device sh would run `echo injected` as a second command.
    assert adb.shell(["echo", "a b; echo injected"]).strip() == "a b; echo injected"
    assert adb.shell(["echo", "it's $HOME"]).strip() == "it's $HOME"


def test_device_is_booted(serial):
    adb = AdbClient(serial)
    wait_for_boot(adb, timeout=30)
    assert adb.real_serial


def test_exec_out_screenshot_is_a_png(serial):
    assert AdbClient(serial).exec_out("screencap -p")[:8] == b"\x89PNG\r\n\x1a\n"

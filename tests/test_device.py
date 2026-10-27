import pytest

from geppetto import By, DeviceTimeoutError
from geppetto.ui.bounds import Bounds

from .conftest import FakeU2


def test_input_text_keeps_every_word(device, adb_run):
    device.input_text("olá mundo; rm -rf /")
    assert adb_run.shell_lines()[-1] == "input text 'olá%smundo;%srm%s-rf%s/'"


def test_input_text_can_hide_secrets_from_the_log(device, caplog):
    with caplog.at_level("INFO", logger="geppetto"):
        device.input_text("s3cr3t", log_text=False)
    assert "s3cr3t" not in caplog.text


def test_user_values_cannot_inject_commands(device, adb_run):
    device.open_app("com.app; reboot")
    device.kill_app("com.app && rm -rf /sdcard")
    device.make_call("123;reboot")
    assert adb_run.shell_lines() == [
        "monkey -p 'com.app; reboot' -c android.intent.category.LAUNCHER 1",
        "am force-stop 'com.app && rm -rf /sdcard'",
        "am start -a android.intent.action.CALL -d 'tel:123;reboot'",
    ]


def test_is_installed_is_an_exact_match(device, adb_run):
    adb_run.responder = lambda argv: "package:com.app.debug\npackage:com.app.beta\n"
    assert device.is_installed("com.app") is False
    adb_run.responder = lambda argv: "package:com.app.debug\npackage:com.app\n"
    assert device.is_installed("com.app") is True


def test_await_widget_by_xpath_uses_u2_xpath(device):
    widget = device.await_widget(By.XPATH, "//node[@resource-id='com.app:id/login']")
    assert widget.text == "Login"
    assert device._u2.selectors == [{"xpath": "//node[@resource-id='com.app:id/login']"}]


def test_await_widget_maps_the_other_strategies(device):
    device.await_widget(By.ID, "com.app:id/login")
    device.await_widget(By.CONTENT_DESC, "Deny")
    assert device._u2.selectors == [{"resourceId": "com.app:id/login"}, {"description": "Deny"}]


def test_await_widget_times_out(device):
    device._u2 = FakeU2(appears=False)
    with pytest.raises(DeviceTimeoutError):
        device.await_widget(By.TEXT, "Nope", timeout=0)


def test_drag_and_drop_uses_draganddrop(device, adb_run):
    device.drag_and_drop(Bounds("[0,0][10,10]"), Bounds("[100,100][110,110]"), duration=500)
    assert adb_run.shell_lines()[-1] == "input draganddrop 5.0 5.0 105.0 105.0 500"


def test_screenshot_pulled_goes_to_images_screenshots(device, adb_run):
    adb_run.responder = lambda argv: b"\x89PNG" if "exec-out" in argv else ""
    path = device.screenshot("login", pull_to_results=True)
    assert path.endswith("Images/Screenshots/login.png")
    assert open(path, "rb").read() == b"\x89PNG"


def test_wait_for_boot_returns_when_boot_completed(device, adb_run):
    adb_run.responder = lambda argv: "1\n"
    device.wait_for_boot(timeout=1)


def test_wait_for_boot_times_out(device, adb_run, monkeypatch):
    monkeypatch.setattr("geppetto.core.adb.time.sleep", lambda s: None)
    adb_run.responder = lambda argv: "0\n"
    with pytest.raises(DeviceTimeoutError):
        device.wait_for_boot(timeout=0)

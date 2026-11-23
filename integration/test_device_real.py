"""Device (uiautomator2) against a real device: hierarchy, waits and app control."""

import pytest

from geppetto import By, DeviceTimeoutError

from .conftest import make_device

SETTINGS = "com.android.settings"


@pytest.fixture(scope="module")
def dev(serial, tmp_path_factory, pytestconfig):
    device = make_device(pytestconfig, serial, tmp_path_factory.mktemp("results"))
    try:
        yield device
    finally:
        device.close()


def test_settings_opens_and_the_hierarchy_is_parsed(dev):
    dev.kill_app(SETTINGS)
    dev.open_app(SETTINGS)
    assert dev.await_for_activity(SETTINGS, timeout=20)
    widget = dev.await_widget(By.XPATH, f"//node[@package='{SETTINGS}']", timeout=20)
    assert widget.package == SETTINGS and widget.bounds is not None
    dev.kill_app(SETTINGS)


def test_is_installed_is_exact(dev):
    assert dev.is_installed(SETTINGS)
    assert not dev.is_installed("com.android")  # a prefix of many packages


def test_await_widget_times_out(dev):
    with pytest.raises(DeviceTimeoutError):
        dev.await_widget(By.TEXT, "geppetto-text-that-does-not-exist", timeout=2)


def test_pulled_screenshot(dev):
    caminho = dev.screenshot("integration", pull_to_results=True)
    assert open(caminho, "rb").read(4) == b"\x89PNG"

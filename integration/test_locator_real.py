"""Locators and expect() against a real device: Settings search, auto-wait and fill."""

import pytest

from geppetto import By, Device, DeviceTimeoutError, ExpectationError, expect

SETTINGS = "com.android.settings"
#: Settings search runs in its own package on Google images; left open, it hides Settings.
SETTINGS_SEARCH = "com.google.android.settings.intelligence"
SEARCH_BAR = f"{SETTINGS}:id/search_action_bar"
EDIT_TEXT = "android.widget.EditText"


@pytest.fixture(scope="module")
def dev(serial, tmp_path_factory):
    return Device(serial, output_dir=tmp_path_factory.mktemp("results"), log_to_console=False)


@pytest.fixture
def settings(dev):
    dev.kill_app(SETTINGS)
    dev.open_app(SETTINGS)
    assert dev.await_for_activity(SETTINGS, timeout=20)
    yield dev
    dev.kill_app(SETTINGS_SEARCH)
    dev.kill_app(SETTINGS)
    dev.key_event(3)  # HOME: leave nothing of Settings on top for the next test


def test_actions_wait_for_the_screen(settings):
    # Settings resumes before its list is drawn: the locator waits instead of the test.
    expect(settings.get(By.XPATH, f"//node[@package='{SETTINGS}']"), timeout=20).to_be_visible()
    settings.get(By.ID, SEARCH_BAR).click(timeout=20)
    field = settings.get(By.CLASS, EDIT_TEXT)
    field.fill("wifi")
    expect(field).to_have_text("wifi")
    field.fill("bluetooth")  # fill() clears what was typed before
    expect(field).to_have_text("bluetooth")
    expect(settings.get(By.CLASS, EDIT_TEXT, exact=False)).to_have_count(1)


def test_timeouts_carry_the_last_observed_state(settings):
    with pytest.raises(DeviceTimeoutError, match="0 matches"):
        settings.get(By.TEXT, "geppetto-text-that-does-not-exist").click(timeout=2)
    with pytest.raises(ExpectationError, match="last seen: 0 matches"):
        expect(
            settings.get(By.TEXT, "geppetto-text-that-does-not-exist"), timeout=2
        ).to_be_visible()
    expect(settings.get(By.TEXT, "geppetto-text-that-does-not-exist")).to_be_hidden()

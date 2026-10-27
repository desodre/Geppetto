import pytest

SETTINGS = "com.android.settings"


def test_settings_opens(settings):
    assert settings.await_for_activity(SETTINGS, timeout=10)


@pytest.mark.xfail(reason="fails on purpose to show the failure artifacts", strict=True)
def test_wrong_screen_on_purpose(settings):
    assert settings.await_for_activity("com.example.does.not.exist", timeout=3)

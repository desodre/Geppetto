"""An expected failure that demonstrates real failure artifacts."""

import pytest

from geppetto import Device


@pytest.mark.xfail(strict=True, reason="intentional failure to demonstrate artifacts")
def test_artifacts(device: Device) -> None:
    device.open_app("com.android.settings")
    assert device.await_for_activity("com.android.settings", timeout=20)
    raise AssertionError("inspect screenshot, hierarchy, logcat and video")

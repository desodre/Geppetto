"""Optional: customise how each Device is created (here, a different result folder name)."""

import pytest

from geppetto import Device


@pytest.fixture(scope="session")
def geppetto_device_factory():
    def factory(serial: str) -> Device:
        return Device(serial, output_dir="results", log_to_console=False)

    return factory


@pytest.fixture
def settings(device):
    """The Settings app opened fresh for each test, closed afterwards."""
    device.kill_app("com.android.settings")
    device.open_app("com.android.settings")
    yield device
    device.kill_app("com.android.settings")

"""Run with two explicit --serial values on authorized lab devices or emulators."""

import pytest

from geppetto import Device


def test_two_devices(devices: list[Device]) -> None:
    if len(devices) < 2:
        pytest.skip("select two devices with --serial SERIAL1 --serial SERIAL2")
    first, second = devices[:2]
    assert first.serial != second.serial
    for device in (first, second):
        assert device.get_os()
        device.screenshot("two-devices", pull_to_results=True)

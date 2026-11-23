"""A typed helper; mypy checks this without connecting a device."""

from geppetto import By, Device, Widget


def login_button(device: Device) -> Widget:
    return device.get(By.ID, "com.example:id/login").widget(timeout=10)

"""A typed helper; mypy checks this without connecting a device."""

from geppetto import By, Device, Widget


def login_button(device: Device) -> Widget:
    return device.await_widget(By.ID, "com.example:id/login", timeout=10)

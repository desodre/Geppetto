from enum import Enum


class WifiSecurityType(Enum):
    """Wi-Fi security protocols supported by Android's cmd wifi."""

    OPEN = "open"
    WPA2 = "wpa2"
    WPA3 = "wpa3"
    OWE = "owe"
    WEP = "wep"

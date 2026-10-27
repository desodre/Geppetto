from geppetto import WifiSecurityType
from geppetto.services.lockscreen import LockscreenService
from geppetto.services.wifi import WifiService


def test_lockscreen_never_logs_the_credential(adb, adb_run, caplog):
    service = LockscreenService(adb)
    with caplog.at_level("INFO"):
        service.set_pin("1234")
        service.set_password("p@ss word")
        service.verify()
        service.clear()
    assert "1234" not in caplog.text and "p@ss" not in caplog.text
    assert "1234" not in repr(service)
    assert adb_run.shell_lines() == [
        "locksettings set-pin 1234",
        "locksettings set-password --old 1234 'p@ss word'",
        "locksettings verify --old 'p@ss word'",
        "locksettings clear --old 'p@ss word'",
    ]
    assert service.password is None


def test_wifi_password_with_spaces_and_symbols(adb, adb_run, caplog):
    with caplog.at_level("INFO"):
        WifiService(adb).connect("Café 5G", WifiSecurityType.WPA2, "a b;$c")
    assert adb_run.shell_lines() == [
        f"cmd wifi connect-network {'Café 5G'.encode().hex()} wpa2 'a b;$c' -x"
    ]
    assert "a b;$c" not in caplog.text


def test_open_wifi_has_no_password(adb, adb_run):
    WifiService(adb).connect("Free", WifiSecurityType.OPEN, "ignored")
    assert adb_run.shell_lines() == [f"cmd wifi connect-network {b'Free'.hex()} open -x"]

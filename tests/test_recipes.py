import sys

import pytest

from examples.recipes import boot_time


def test_boot_recipe_measures_elapsed_time_and_stops_its_emulator(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["boot_time.py", "Dedicated_AVD", "--gpu", "host"])
    clock = iter([10.0, 13.5])
    monkeypatch.setattr(boot_time.time, "monotonic", lambda: next(clock))
    calls = []

    def start(avd, **kwargs):
        calls.append((avd, kwargs))
        return "emulator-5554"

    monkeypatch.setattr(boot_time.emulator, "start", start)
    monkeypatch.setattr(boot_time.emulator, "stop", lambda serial: calls.append(serial))
    boot_time.main()
    assert "sys.boot_completed after 3.50s" in capsys.readouterr().out
    assert calls == [
        (
            "Dedicated_AVD",
            {
                "headless": True,
                "extra_args": ["-gpu", "host", "-no-snapshot-load", "-no-snapshot-save"],
                "timeout": 180,
            },
        ),
        "emulator-5554",
    ]


def test_boot_recipe_stops_the_device_even_if_reporting_fails(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["boot_time.py", "Dedicated_AVD"])
    monkeypatch.setattr(boot_time.emulator, "start", lambda *args, **kwargs: "emulator-5554")
    stopped = []
    monkeypatch.setattr(boot_time.emulator, "stop", stopped.append)

    def broken_output(*args):
        raise OSError("output closed")

    monkeypatch.setattr("builtins.print", broken_output)
    with pytest.raises(OSError, match="output closed"):
        boot_time.main()
    assert stopped == ["emulator-5554"]

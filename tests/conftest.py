"""Fixtures that run Geppetto without a device: adb is replaced by a recorder."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from geppetto import Device
from geppetto.core import adb as adb_module
from geppetto.core.adb import AdbClient, device_command

DUMP = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.app"
        content-desc="" clickable="false" enabled="true" bounds="[0,0][1080,2340]">
    <node index="0" text="Don't allow" resource-id="com.app:id/deny" class="android.widget.Button"
          package="com.app" content-desc="Deny" clickable="true" enabled="true"
          bounds="[100,200][500,300]" />
    <node index="1" text="Login" resource-id="com.app:id/login" class="android.widget.Button"
          package="com.app" content-desc="" clickable="true" enabled="true"
          bounds="[100,400][500,500]">
      <node index="0" text="Login" resource-id="" class="android.widget.TextView"
            package="com.app" content-desc="" bounds="[120,420][480,480]" />
    </node>
  </node>
</hierarchy>
"""


@dataclass
class AdbRecorder:
    """Stands in for ``subprocess.run``: records argv and answers through *responder*."""

    calls: list[list[str]] = field(default_factory=list)
    responder: Callable[[list[str]], str | bytes] = lambda argv: ""

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[object]:
        self.calls.append(list(argv))
        out = self.responder(list(argv))
        if not kwargs.get("text") and isinstance(out, str):
            out = out.encode()
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

    def shell_lines(self) -> list[str]:
        """What reached the device shell, one string per ``adb shell`` call."""
        return [argv[4] for argv in self.calls if argv[3:4] == ["shell"]]


@pytest.fixture
def adb_run(monkeypatch: pytest.MonkeyPatch) -> AdbRecorder:
    recorder = AdbRecorder(
        responder=lambda argv: "SERIAL123\n" if "ro.serialno" in argv[-1] else ""
    )
    monkeypatch.setattr(adb_module.subprocess, "run", recorder)
    return recorder


@pytest.fixture
def adb(adb_run: AdbRecorder) -> AdbClient:
    client = AdbClient("SERIAL123")
    adb_run.calls.clear()
    return client


class FakeU2:
    """The bits of ``uiautomator2.Device`` that :class:`Device` touches."""

    def __init__(self, dump: str = DUMP, appears: bool = True) -> None:
        self.dump, self.appears, self.selectors = dump, appears, []

    def __call__(self, **selector: str) -> FakeU2:
        self.selectors.append(selector)
        return self

    def xpath(self, value: str) -> FakeU2:
        self.selectors.append({"xpath": value})
        return self

    def wait(self, timeout: float) -> bool:
        return self.appears

    def dump_hierarchy(self) -> str:
        return self.dump


@pytest.fixture
def device(adb: AdbClient, tmp_path) -> Device:
    """A Device wired to the recorder and a fake uiautomator2, without touching hardware."""
    dev = object.__new__(Device)
    dev._serial = "SERIAL123"
    dev.adb = adb
    dev._u2 = FakeU2()
    dev.result_path = tmp_path
    dev.logger = logging.getLogger("geppetto.test.device")
    return dev


__all__ = ["DUMP", "AdbRecorder", "FakeU2", "device_command"]

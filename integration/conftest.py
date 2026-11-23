"""Integration tests: a real Android device or emulator, chosen like the plugin does
(``--serial``, ``GEPPETTO_SERIAL`` or the only connected device).

Run: ``uv run pytest integration --geppetto-artifacts=on-failure``. Without a device every test
is skipped. CI runs them on an emulator (``.github/workflows/dev.yml``).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from geppetto import Device

pytest_plugins = ["pytester"]


def make_device(pytestconfig: pytest.Config, serial: str, output_dir: Path) -> Device:
    """Create a :class:`Device` using the configured pytest UI backend options."""
    backend = str(
        pytestconfig.getoption("geppetto_backend")
        or os.environ.get("GEPPETTO_BACKEND")
        or "uiautomator2"
    )
    carlo_binary = (
        pytestconfig.getoption("geppetto_carlo_binary")
        or os.environ.get("GEPPETTO_CARLO_BINARY")
        or None
    )
    if backend == "uiautomator2":
        return Device(serial, output_dir=output_dir, log_to_console=False)
    return Device(
        serial,
        output_dir=output_dir,
        log_to_console=False,
        backend=backend,
        carlo_binary=carlo_binary,
    )


@pytest.fixture(scope="session")
def serial(geppetto_serials: list[str]) -> str:
    if not geppetto_serials:
        pytest.skip("integration tests need a device or emulator (--serial / GEPPETTO_SERIAL)")
    return geppetto_serials[0]


def geppetto(*args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    """Run the installed ``geppetto`` console script."""
    executable = shutil.which("geppetto") or str(Path(sys.executable).with_name("geppetto"))
    return subprocess.run([executable, *args], capture_output=True, text=True, timeout=timeout)

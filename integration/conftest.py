"""Integration tests: a real Android device or emulator, chosen like the plugin does
(``--serial``, ``GEPPETTO_SERIAL`` or the only connected device).

Run: ``uv run pytest integration --geppetto-artifacts=on-failure``. Without a device every test
is skipped. CI runs them on an emulator (``.github/workflows/dev.yml``).
"""

import subprocess

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture(scope="session")
def serial(geppetto_serials: list[str]) -> str:
    if not geppetto_serials:
        pytest.skip("integration tests need a device or emulator (--serial / GEPPETTO_SERIAL)")
    return geppetto_serials[0]


def geppetto(*args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    """Run the installed ``geppetto`` console script."""
    return subprocess.run(["geppetto", *args], capture_output=True, text=True, timeout=timeout)

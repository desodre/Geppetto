# Geppetto — Copilot Instructions

Geppetto is a high-level Python framework for Android UI automation, orchestrating ADB, Fastboot, and UIAutomator2 behind a unified API.

## Commands

```bash
uv sync --all-extras          # Install all dependencies (including optional extras)

uv run ruff check src         # Lint
uv run ruff format src        # Format
uv run mypy src               # Type-check (strict mode)
uv run pytest                 # Run all tests
uv run pytest tests/path/to_test.py::test_name  # Run a single test
```

## Architecture

`Device` (`src/geppetto/device.py`) is the primary facade and entry point. It composes:

- **`core/adb.py`** — `AdbClient`: low-level ADB transport. Uses `subprocess` without `shell=True` to prevent injection. Exposes `.shell()`, `.cmd()`, `.async_shell()`, and file ops.
- **`core/fastboot.py`** — `FastbootClient`: Fastboot transport layer.
- **`ui/`** — UI models parsed from `uiautomator2`'s XML hierarchy dumps:
  - `WindowDump`: lazily parses the XML with `lxml.etree` and provides `.find_widget(by, value)` / `.get_widgets()`.
  - `Widget`: dataclass representing one UI node; built via `Widget.from_xml_node()` or `Widget.from_dict()`.
  - `Bounds`: parses Android's `[x1,y1][x2,y2]` string format; provides geometric helpers (`.center`, `.contains()`, etc.).
  - `Children`: thin wrapper over a list of `Widget`.
- **`services/`** — `WifiService`, `LockscreenService`, `NotificationService`; each takes an `AdbClient` in `__init__` and is exposed as `device.wifi`, `device.lockscreen`, `device.notification`.
- **`models/`** — Enums: `By` (widget selector strategy), `Direction`, `WifiSecurityType`.
- **`analyzers/`** and **`hardware/`** — optional extras (`opencv`, `imagehash`, `brainstem`). Imported lazily in `__init__.py` via `__getattr__` so missing extras don't break core imports.
- **`_logging.py`** — `DeviceLogger` factory; writes structured logs to `<result_dir>/Logs/`.

`Device.__init__` creates a timestamped result directory (`./results/<timestamp>_<serial>/`) with `Screenshots/`, `Pictures/`, and `Logs/` subdirectories.

## Key Conventions

- **Python 3.12+** strictly required. Use `from __future__ import annotations` in every module.
- **Strict mypy** (`strict = true`). Add `ignore_missing_imports = true` overrides for third-party stubs in `pyproject.toml`.
- **XML parsing**: always use `lxml.etree`, never `xml.etree.ElementTree`.
- **ADB commands**: go through `AdbClient.shell()` or `AdbClient.cmd()` — never call `subprocess` directly in higher-level code, and never use `shell=True`.
- **Services** receive an `AdbClient` instance; they do not hold a reference to `Device`.
- **Exception naming**: suffix with `Error` (e.g., `WidgetNotFoundError`). Re-raise with `raise ... from err` or `raise ... from None`.
- **`By` enum values** map directly to `Widget` attribute names (e.g., `By.TEXT` → `widget.text`), except `By.XPATH` which triggers an XPath query on the raw XML.
- **SSID encoding** in `WifiService.connect()`: SSIDs are hex-encoded before passing to `cmd wifi` to avoid shell-escaping issues.
- **Optional dependencies**: expose via `__getattr__` in `__init__.py` for lazy import; guard with `TYPE_CHECKING` where needed.
- **Ruff** enforces `E`, `F`, `I`, `N`, `W`, `B` rules with a line-length of 100.

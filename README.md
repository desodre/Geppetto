# geppetto-android

Geppetto is a high-level Python framework for Android UI automation.
It provides a single, typed API to orchestrate ADB, Fastboot, and UIAutomator2.

Just as Geppetto brought Pinocchio to life, this tool brings your Android tests to life.

## Highlights

- High-level `Device` facade for Android automation workflows.
- Widget search through text, id, class, content description, and XPath.
- Structured UI hierarchy parsing via `lxml` (`WindowDump`, `Widget`, `Bounds`).
- Built-in services for Wi-Fi, lockscreen, and notification controls.
- Optional extras for image/video analyzers and hardware integrations.
- User values (packages, text, passwords) are quoted for the device shell: no command injection.

## Requirements

- Python 3.12+
- Android SDK platform tools (`adb`, optional `fastboot`) available on PATH
- Android device or emulator with ADB enabled

## Installation

### pip

```bash
pip install geppetto-android
```

Optional extras:

```bash
# Image/video analyzers (Pillow, OpenCV, imagehash…)
pip install "geppetto-android[analyzers]"

# Hardware integrations
pip install "geppetto-android[hardware]"

# All optional features
pip install "geppetto-android[all]"
```

### uv

```bash
uv add geppetto-android
uv add "geppetto-android[analyzers]"
uv add "geppetto-android[hardware]"
uv add "geppetto-android[all]"
```

## Quick start

```python
from geppetto import By, Device, WifiSecurityType

device = Device("SERIAL_NUMBER")

device.install("app.apk", replace=True)
device.open_app("com.example.app")

login_button = device.await_widget(By.TEXT, "Login", timeout=15)
device.click(login_button)

device.input_text("hello world")              # spaces are kept
device.input_text("s3cr3t", log_text=False)    # secrets stay out of the logs

# Saved under <output_dir>/<run>_<serial>/Images/Screenshots/login_screen.png
device.screenshot("login_screen", pull_to_results=True)

device.wifi.connect("MyNetwork", WifiSecurityType.WPA2, "password")
```

### Errors

Every exception derives from `GeppettoError`:

| Exception | When |
|---|---|
| `DeviceNotFoundError` | the serial does not answer adb (offline, unauthorized, wrong serial) |
| `DeviceTimeoutError` | a widget, activity or boot did not show up in time |
| `WidgetNotFoundError` | no widget matches the search in a `WindowDump` |
| `DeviceIsSecureError` | `adb root` refused on a secure build |

### Logging

Geppetto logs under the `geppetto` logger hierarchy and adds only a `NullHandler` to it, so your
own logging configuration (or pytest's `caplog`) receives every record. `Device` also prints to
the console and writes `Logs/device.log`/`Logs/adb.log` in its result folder; turn that off with
`Device(serial, log_to_console=False, log_to_file=False)`.

## Main components

- `Device`: primary facade and entry point.
- `geppetto.core`: ADB/Fastboot clients.
- `geppetto.ui`: UI models (`WindowDump`, `Widget`, `Bounds`, `Children`).
- `geppetto.services`: automation services (`wifi`, `lockscreen`, `notification`).
- `geppetto.models`: enums such as `By`, `Direction`, `WifiSecurityType`, `CommonClasses`.

## Development

```bash
git clone https://github.com/desodre/geppetto.git
cd geppetto
uv sync --group dev --all-extras

uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src
uv run pytest          # no device needed: adb is replaced by a recorder
```

The version lives only in `src/geppetto/__init__.py` (`__version__`); `pyproject.toml` reads it.
Publishing is a `vX.Y.Z` tag that matches it; CI must pass first.

## Links

- Homepage: https://github.com/desodre/geppetto
- Repository: https://github.com/desodre/geppetto
- Issues: https://github.com/desodre/geppetto/issues

## License

MIT License

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
# Image/video analyzers
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

device.screenshot("login_screen", pull_to_results=True)

device.wifi.connect("MyNetwork", WifiSecurityType.WPA2, "password")
```

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
uv sync --all-extras
```

## Links

- Homepage: https://github.com/desodre/geppetto
- Repository: https://github.com/desodre/geppetto
- Issues: https://github.com/desodre/geppetto/issues

## License

MIT License

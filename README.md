# Geppetto

> Just as Geppetto brought Pinocchio to life, this tool brings your tests to life through automation.

## Overview

Geppetto is an Android UI automation framework that orchestrates and executes your test suite
with precision and care. It provides a high-level Python API for controlling Android devices
via ADB, Fastboot, and UIAutomator2.

## Installation

```bash
uv add geppetto

# With image/video analysis support
uv add geppetto --optional analyzers

# With Acroname USB hub support
uv add geppetto --optional hardware

# Everything
uv add geppetto --optional all
```

For development:

```bash
# Clone the repository
git clone <repo-url>
cd geppetto

# Install dependencies and create virtual environment
uv sync --all-extras
```

## Quick Start

```python
from geppetto import Device, By

device = Device("SERIAL_NUMBER")

# Install and open an app
device.install("app.apk", replace=True)
device.open_app("com.example.app")

# Find and interact with UI elements
widget = device.await_widget(By.TEXT, "Login", timeout=15)
device.click(widget)

# Take a screenshot
device.screenshot("login_screen", pull_to_results=True)

# Access sub-services
device.wifi.connect("MyNetwork", WifiSecurityType.WPA2, "password")
device.lockscreen.set_pin("1234")
device.notification.open()
```

## Architecture

```
geppetto/
├── core/        # ADB & Fastboot transport layers
├── ui/          # Widget, Bounds, WindowDump, Children
├── services/    # Lockscreen, WiFi, Notification controllers
├── analyzers/   # Screen and Video analysis tools
├── hardware/    # External hardware (Acroname USB hub)
├── models/      # Enums (By, Direction, WifiSecurityType)
├── device.py    # Main Device class (composition-based)
└── exceptions.py
```

## License

MIT

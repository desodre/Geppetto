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

# QR-code pairing in the CLI (`geppetto pair --qr`)
pip install "geppetto-android[cli]"

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
| `AdbCommandError` | a host-side adb command failed (message has adb's output) |
| `EmulatorError` | emulator missing, unknown AVD, or the emulator exited while starting |
| `LogNotFoundError` | `expect()` timed out, or `expect_no()` saw the line |
| `AppCrashedError` | a watched app crashed, ANR'd or died by a native signal |

### Logging

Geppetto logs under the `geppetto` logger hierarchy and adds only a `NullHandler` to it, so your
own logging configuration (or pytest's `caplog`) receives every record. `Device` also prints to
the console and writes `Logs/device.log`/`Logs/adb.log` in its result folder; turn that off with
`Device(serial, log_to_console=False, log_to_file=False)`.

## pytest plugin

Installing Geppetto registers a pytest plugin. Ask for the `device` (or `devices`) fixture:

```python
def test_settings_opens(device):
    device.open_app("com.android.settings")
    assert device.await_for_activity("com.android.settings")
```

```bash
pytest                                   # the only connected device is picked
pytest --serial emulator-5554            # repeat --serial for several (or GEPPETTO_SERIAL=a,b)
pytest --all-devices                     # every device adb reports as ready
pytest --geppetto-record --html=report.html --self-contained-html
```

When a device test fails (including `xfail`), Geppetto saves in
`<output>/<run>_<serial>/Tests/<test id>/`:

| File | What |
|---|---|
| `screenshot.png` | the screen at the failure (embedded in the pytest-html report) |
| `window_dump.xml` | the UI hierarchy at the failure |
| `logcat.txt` | the log produced by the test (logcat is cleared before each device test) |
| `screenrecord.mp4` | the whole test, with `--geppetto-record` (Android caps it at 180 s) |

The folder is printed in the failure report and written as a JUnit property
`geppetto_artifacts[<serial>]`. Options: `--geppetto-output DIR`,
`--geppetto-artifacts on-failure|always|never` (also as `geppetto_output` / `geppetto_artifacts`
in `[tool.pytest.ini_options]`). Without a device, tests that need one are skipped with the reason.
Override the `geppetto_device_factory` fixture in `conftest.py` to customise how each `Device` is
created. A runnable example lives in [`examples/pytest`](examples/pytest).

## Logcat and crash detection

```python
with device.logcat(package="com.example", level="I") as log:    # from now on, nothing cleared
    device.click(device.await_widget(By.ID, "com.example:id/pay"))
    log.expect(r"Payment OK", timeout=10)                       # waits for a new matching line
    log.expect_no("Exception", within=2)                        # fails if one shows up

with device.watch_crashes("com.example"):                       # AppCrashedError at the end of
    device.click(...)                                            # the block, with the stack trace
```

Filters: `package` (follows the app across restarts), `tags`, minimum `level` (`V D I W E F`)
and a `pattern` regex. Crashes detected: Java (`FATAL EXCEPTION` + stack), ANR (`ANR in …` +
reason) and native signals (`Fatal signal …` + backtrace and tombstone path).

In pytest, `--geppetto-watch com.example` (or `geppetto_watch` in the ini, or
`@pytest.mark.geppetto_watch("com.example")`) fails a device test when that app crashes during it,
even if its assertions passed, and saves `crash.txt` with the artifacts. Only the packages you name
are watched, so an unrelated system ANR on a slow emulator does not fail your tests.

## Command line

```bash
geppetto devices                      # every device adb knows (state, usb/wi-fi/emulator, model)
geppetto doctor                       # adb, devices, uiautomator2 agent, emulator, extras — with fixes
geppetto shot -o login.png            # screenshot (-s SERIAL; default: the only device)
geppetto record -t 30 -o flow.mp4     # screen recording, Ctrl+C stops earlier (max 180 s)

geppetto emulator list
geppetto emulator start Pixel_8_API_35 --headless     # returns when Android finished booting
geppetto emulator snapshot save clean -s emulator-5554
geppetto emulator stop emulator-5554

geppetto pair 192.168.0.10:40111 123456   # Wireless debugging › Pair device with pairing code
geppetto pair --qr                        # …or scan a QR code (pip install 'geppetto-android[cli]')
geppetto connect 192.168.0.10:37000

geppetto inspect                          # screen + selectors in the browser, records code
```

### Inspector

```bash
geppetto inspect            # opens http://127.0.0.1:8765/ for the only connected device
```

The device screen in your browser. Hover to highlight elements; click one to see its attributes and
the **recommended selector** (the most stable one that matches only that element: resource-id,
content-desc, text, id + text, relative to a parent with a unique id, and only as a last resort a
position, flagged as fragile). Switch to **Record** and your taps, typing and Back/Home presses are
executed on the device and turned into a runnable script (copy or download it):

```python
from geppetto import By, Device


def main() -> None:
    device = Device('emulator-5554')
    device.click(device.await_widget(By.ID, 'com.android.settings:id/search_action_bar'))
    device.input_text('wifi')
```

It listens on `127.0.0.1` only (the page can tap and type on the device); `--host` exposes it on
purpose, `--port 0` picks a free port. The first run installs the uiautomator2 agent on the device.

Commands that need one device take `-s/--serial`, then `GEPPETTO_SERIAL`, then the only ready
device. Errors print one line on stderr and exit with 1. `geppetto doctor` exits with 1 when a
check fails. The emulator is found on PATH or in the SDK (`ANDROID_SDK_ROOT`, `ANDROID_HOME`, or
the default install folder).

## Main components

- `Device`: primary facade and entry point.
- `geppetto.pytest_plugin`: fixtures, CLI options and failure artifacts for pytest.
- `geppetto` command line (`geppetto.cli`): devices, doctor, shot, record, emulator, pairing, inspect.
- `geppetto.inspector`: selector recommendation, code recorder and the local web inspector.
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

# integration tests on a real device/emulator (skipped without one)
uv run pytest integration --serial emulator-5554 --geppetto-artifacts=on-failure
```

CI: pushes and PRs to `dev` run the unit tests and, on a separate runner, the integration tests on
an Android emulator (`.github/workflows/dev.yml`); `main` and the PyPI publish run `ci.yml`.

The version lives only in `src/geppetto/__init__.py` (`__version__`); `pyproject.toml` reads it.
Publishing is a `vX.Y.Z` tag that matches it; CI must pass first.

## Links

- Homepage: https://github.com/desodre/geppetto
- Repository: https://github.com/desodre/geppetto
- Issues: https://github.com/desodre/geppetto/issues

## License

MIT License

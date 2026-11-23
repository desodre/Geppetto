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

See [versioning and support](CONTRIBUTING.md#versioning-and-public-api) for the tested matrix,
deprecation guarantees and release process. The package includes `py.typed` for type checkers.

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
from geppetto import By, Device, WifiSecurityType, expect

device = Device("SERIAL_NUMBER")

device.install("app.apk", replace=True)
device.open_app("com.example.app")

device.get(By.ID, "com.example.app:id/username").fill("hello world")   # waits, then types
device.get(By.ID, "com.example.app:id/password").fill("s3cr3t", log_text=False)
device.get(By.TEXT, "Login").click()                                    # waits for the button
expect(device.get(By.TEXT, "Welcome")).to_be_visible()                  # retries until timeout

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
| `LogNotFoundError` | `log.expect()` timed out, or `log.expect_no()` saw the line |
| `AppCrashedError` | a watched app crashed, ANR'd or died by a native signal |
| `ExpectationError` | an `expect(locator)` assertion did not hold in time (also an `AssertionError`) |

### Logging

Geppetto logs under the `geppetto` logger hierarchy and adds only a `NullHandler` to it, so your
own logging configuration (or pytest's `caplog`) receives every record. `Device` also prints to
the console and writes `Logs/device.log`/`Logs/adb.log` in its result folder; turn that off with
`Device(serial, log_to_console=False, log_to_file=False)`.

## Locators and `expect()`

`device.get(by, value)` returns a lazy `Locator`: nothing is looked up until you act on it, and
every action waits (up to `device.default_timeout`, 10 s) for the element to be visible and
enabled. No `sleep`, no manual `await_widget` before each tap.

```python
from geppetto import By, expect

device.get(By.ID, "com.app:id/email").fill("me@example.com")   # tap, clear, type
device.get(By.TEXT, "Sign in").click()
device.get(By.TEXT, "Help").long_press()
device.get(By.ID, "com.app:id/item").first.swipe_to(device.get(By.TEXT, "Trash"))

expect(device.get(By.ID, "com.app:id/error")).to_have_text("Invalid password")
expect(device.get(By.TEXT, "Signing in…")).to_be_hidden()
expect(device.get(By.ID, "com.app:id/row")).to_have_count(3)
expect(device.get(By.TEXT, "Remember me")).not_.to_be_checked()
```

Refine a locator by chaining (each call returns a new one):

| Call | Meaning |
|---|---|
| `.get(by, value)` | descendants of the current matches |
| `.filter(by, value)` / `.filter(has=loc)` | same node must also match / must contain a match of `loc` |
| `.within(loc)` | inside the first match of `loc` |
| `.below(loc)`, `.above(loc)`, `.right_of(loc)`, `.left_of(loc)` | on that side of `loc`, closest first |
| `.nth(i)`, `.first`, `.last` | one match by position |
| `exact=False` | case-insensitive substring; a compiled regex as `value` matches with `search()` |

```python
rows = device.get(By.ID, "com.android.settings:id/recycler_view").get(By.CLASS, "android.widget.LinearLayout")
rows.filter(has=device.get(By.TEXT, "Bluetooth")).get(By.CLASS, "android.widget.Switch").click()
device.get(By.CLASS, "android.widget.EditText").below(device.get(By.TEXT, "Email")).fill("me@x.io")
device.get(By.TEXT, re.compile(r"^Wi.?Fi$")).click()
```

Reads: `loc.widget()` waits for the first match and returns the `Widget` (children included);
`loc.all()`, `loc.count()`, `loc.is_visible()`, `loc.is_enabled()`, `loc.is_checked()` answer
right now, without waiting; `loc.wait_for("visible" | "hidden" | "enabled" | "attached")`.

Assertions: `to_be_visible`, `to_be_hidden`, `to_be_enabled`, `to_be_disabled`, `to_be_checked`,
`to_be_selected`, `to_be_focused`, `to_have_text(text | regex, exact=True)`, `to_contain_text`,
`to_have_content_desc`, `to_have_count`; all take `timeout=` and are negated with `.not_`.
A failed expectation raises `ExpectationError` (an `AssertionError` too) whose message carries the
expectation and the last state seen, e.g. `Expected device.get(By.ID, 'com.app:id/error') to be text
'Invalid password' (waited 10s); last seen: text 'Signing in…'`. Timeouts from actions
(`DeviceTimeoutError`) do the same: `last seen: 0 matches`, or the widget with `enabled=False`.

### Migrating from `await_widget` / `find_widget`

The old API keeps working and emits no warning: nothing is removed before 3.0, and any removal is
announced with a `DeprecationWarning` one minor release earlier (see the versioning policy). New
code and `geppetto inspect` recordings use locators:

| Before | After |
|---|---|
| `device.click(device.await_widget(By.TEXT, "Login"))` | `device.get(By.TEXT, "Login").click()` |
| `w = device.await_widget(By.ID, rid, timeout=15)` | `w = device.get(By.ID, rid).widget(timeout=15)` |
| `device.get_window_dump().find_widget(By.XPATH, xp)` | `device.get(By.XPATH, xp).widget()` |
| `device.click(field); device.input_text("x")` | `device.get(...).fill("x")` (or `.type_text("x")` to append) |
| `assert device.await_widget(By.ID, rid).text == "x"` | `expect(device.get(By.ID, rid)).to_have_text("x")` |
| `time.sleep(2)` before a lookup | nothing: actions and `expect()` wait |

`Device(serial, default_timeout=20)` changes the wait for every locator of that device.

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
pytest --serial emulator-5554 --html=report.html --self-contained-html
```

When a device test fails (including `xfail`), Geppetto saves in
`<output>/<run>_<serial>/Tests/<test id>/`:

| File | What |
|---|---|
| `screenshot.png` | the screen at the failure (embedded in the pytest-html report) |
| `window_dump.xml` | the UI hierarchy at the failure |
| `logcat.txt` | the last 120 seconds of the test, without clearing device logs |
| `screenrecord.mp4` | the test recording (Android caps it at 180 s) |

The folder is printed in the failure report and written as a JUnit property
`geppetto_artifacts[<serial>]`. Options: `--geppetto-output DIR`,
`--geppetto-artifacts on-failure|always|never`, `--geppetto-logcat-seconds N`, and
`--no-geppetto-record` to disable video (also set `geppetto_output` / `geppetto_artifacts`
in `[tool.pytest.ini_options]`). The `device` fixture has function scope while reusing its
connection during the session; `devices` has session scope. Without a device, tests that need one
are skipped with the reason.
Override the `geppetto_device_factory` fixture in `conftest.py` to customise how each `Device` is
created. A runnable login example and its small Android app live in
[`examples/pytest`](examples/pytest).

## Logcat and crash detection

```python
with device.logcat(package="com.example", level="I") as log:    # from now on, nothing cleared
    device.get(By.ID, "com.example:id/pay").click()
    log.expect(r"Payment OK", timeout=10)                       # waits for a new matching line
    log.expect_no("Exception", within=2)                        # fails if one shows up

with device.watch_crashes("com.example"):                       # AppCrashedError at the end of
    device.get(By.TEXT, "Pay").click()                          # the block, with the stack trace
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
    device.get(By.ID, 'com.android.settings:id/search_action_bar').click()
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
- `geppetto.locator`: `Locator` (auto-waiting actions) and `expect()` (retrying assertions).
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

CI: every PR/push to `main` runs Python 3.12/3.13 checks and API 34 emulator integration.
`dev` reuses this pipeline. Publishing also requires the API 26 compatibility smoke.
Empty or entirely skipped integration runs fail. See [CONTRIBUTING](CONTRIBUTING.md).

Build the documentation with `uv run --group docs mkdocs build --strict`, or preview it with
`uv run --group docs mkdocs serve`. Docs build from static sources without a device or extras.
The site follows main and labels unreleased features; its four recipes cover login, boot time,
two devices and failure artifacts. Pages deployment runs only from main.

The version lives only in `src/geppetto/__init__.py` (`__version__`); `pyproject.toml` reads it.
Publishing is a `vX.Y.Z` tag that matches it; CI must pass first.

## Links

- Documentation: https://desodre.github.io/Geppetto/

- Homepage: https://github.com/desodre/geppetto
- Repository: https://github.com/desodre/geppetto
- Issues: https://github.com/desodre/geppetto/issues

## License

MIT License

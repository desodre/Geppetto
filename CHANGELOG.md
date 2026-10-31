# Changelog

## Unreleased

### Added
- Documentation site with a static API reference, typed examples and executable recipes for
  login, emulator boot time, two devices and failure artifacts; GitHub Pages deploys from main.
- CONTRIBUTING documents SemVer, deprecation and tested Python/Android environments; an internal
  warning helper keeps future deprecations consistent without changing existing aliases.
- **`geppetto inspect`**: the device screen in the browser with hover highlight, element attributes
  and the recommended selector (unique in the dump, stable attributes first, position-based ones
  flagged as fragile); **Record** mode taps/types/presses keys on the device and builds a runnable
  Python script (copy / download). Local-only by default (`--host` to expose, `--port 0` for a free
  port). Standard library only.
- `geppetto.inspector`: `recommend()`/`Selector`, `xpath_literal()`, `Recorder`, `InspectorServer`,
  `hierarchy_json()`.
- **Logcat streaming** (`Device.logcat()`, `LogcatStream`, `LogLine`): live from the device's current
  time, filters by package/tag/level/regex, ring buffer, `expect()` / `expect_no()`
  (`LogNotFoundError`).
- **Crash detection** (`Device.watch_crashes()`, `CrashWatcher`, `Crash`): Java exceptions, ANRs and
  native signals with stack/backtrace/tombstone; `AppCrashedError`. pytest: `--geppetto-watch`,
  ini `geppetto_watch`, marker `geppetto_watch(...)` fail a test when a watched app crashes and add
  `crash.txt` to the artifacts.

### Fixed
- Inspector: clickable rows without attributes of their own (the usual Android list item) get a
  stable selector through their label instead of a fragile position.

### Changed
- API 34 emulator integration now runs for every PR to main and is reused by dev. Release
  validation also requires the API 26 compatibility smoke; empty/all-skipped reports fail.
- GitHub Actions closes referenced issues and their sub-issues after commits or PRs land on `main`.
- The pytest `device` fixture now has function scope while reusing its connection for the session.
  A test using only `device` captures artifacts only from its selected serial.
- Failure artifacts now include video by default (`--no-geppetto-record` disables it). Logcat
  uses a bounded, configurable time window (`--geppetto-logcat-seconds`) without clearing the
  device-wide buffer. Fixture teardown failures keep their artifacts too.
- `examples/pytest` includes a buildable login app and a tested login flow.

## 2.1.0

### Highlights
- **pytest plugin** (registered automatically): `device`/`devices` fixtures, `--serial`
  (repeatable, or `GEPPETTO_SERIAL`), `--all-devices`, `--geppetto-output`,
  `--geppetto-artifacts on-failure|always|never`, `--geppetto-record`; tests without a device are
  skipped with the reason; `geppetto_device_factory` customises creation.
- Failure artifacts for device tests (failures and `xfail`): `screenshot.png`, `window_dump.xml`,
  `logcat.txt` (cleared before each test) and `screenrecord.mp4`, under
  `<result folder>/Tests/<test id>/`; listed in the failure report, as a JUnit property and in
  pytest-html (screenshot embedded).
- `Device.clear_logcat()`, `Device.dump_logcat()`, `Device.start_recording()` and
  `geppetto.recording.ScreenRecording`; `core.adb.list_devices()`, `AdbClient.spawn_shell()`.
- `examples/pytest`: runnable example with the Settings app.
- **`geppetto` command line**: `devices` (`--json`), `doctor` (each problem with its fix, exit 1 on
  failures), `shot`, `record`, `emulator list|start|stop|snapshot`, `pair` (code or `--qr`),
  `connect`, `disconnect`. New extra `[cli]` (`qrcode`) for QR pairing.
- `geppetto.core.host` (devices -l, pair/connect, mDNS), `geppetto.core.emulator` (SDK lookup,
  AVDs, start waiting for the boot, stop, snapshots), `geppetto.doctor`,
  `core.adb.wait_for_boot`; exceptions `AdbCommandError` and `EmulatorError`.

### Fixed
- `Device.input_text` typed only the first word: spaces are now sent as `%s`.
- `Device.await_widget(By.XPATH, …)` used a selector uiautomator2 does not have; it now polls the
  `WindowDump`, so the same `//node[...]` expression works for waiting and for `find_widget`.
- `WindowDump.find_widget` / `set_children` broke on text with an apostrophe (`Don't allow`) and
  could return the children of another node; children now come from the widget's own XML node.
  An XPath that returns a number (e.g. `count(...)`) is a "not found", not a crash.
- `find_widget(By.WIDGET, …)` raised `AttributeError`; it now raises a clear `ValueError`.
- `Device.is_installed("com.app")` was true when only `com.app.debug` existed.
- `Colors.ALMOST_BLUE` was an alias of `ALMOST_GREEN` (same value); the `ALMOST_*` colors are
  now distinct RGB values.
- `ScreenAnalyzer.crop_image` overwrote the original image by default. Saving is now opt-in and
  needs `new_name`.
- `DeviceLogger` crashed when `<result_dir>/Logs` did not exist (e.g. `AcronameController`) and a
  second `Device` with the same serial kept writing to the first run's log file.
- Screenshots/screen recordings went to folders the `Device` did not create; they now go to
  `Images/Screenshots` and `Videos/Screenrecords`. `AdbClient.pull` returns the real local path.
- `Device.reboot` waited a fixed 10 s; it now waits for `sys.boot_completed` (`wait_for_boot`).
- `Device.drag_and_drop` was a plain swipe; it now uses `input draganddrop`.
- `Device.get_os` reads `ro.build.version.release`, present on every build.

### Security
- Values from the caller are quoted for the device shell (`adb shell` re-parses its arguments on
  the device, so `open_app("x; reboot")` used to run `reboot`). `AdbClient.shell` accepts a list
  of arguments for that; a string is still a trusted, raw command line.
- Lock-screen PIN/password and Wi-Fi passwords are no longer written to the logs.
  `input_text(..., log_text=False)` keeps typed secrets out as well.

### Added
- `GeppettoError` base class and `DeviceNotFoundError` (raised when the serial does not answer).
- `Device(..., log_to_console=, log_to_file=)`; loggers live under the `geppetto` hierarchy with a
  `NullHandler`, so applications control logging.
- `AcronameController` is a context manager; `reset_and_close` now really closes.
- `Direction.UP` / `Direction.DOWN` (`Up` / `Down` kept as aliases).
- Integration tests on a real emulator in CI for the `dev` branch (`dev.yml`), next to the unit tests.
- Unit tests (no device needed) and a CI workflow (ruff, mypy, pytest on 3.12/3.13) that the
  PyPI publish depends on; the tag must match the package version.

### Changed
- `pillow` moved to the `analyzers` extra; `adbutils` is no longer a direct dependency.
- The version is read from `geppetto/__init__.py` (single source).
- Install hints in import errors use the published name `geppetto-android[...]`.
- Removed the template `main.py`.

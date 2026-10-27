# Changelog

## 2.1.0

### Fixed
- `Device.input_text` typed only the first word: spaces are now sent as `%s`.
- `Device.await_widget(By.XPATH, …)` used a selector uiautomator2 does not have; it now goes
  through `d.xpath(...)`.
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
- Unit tests (no device needed) and a CI workflow (ruff, mypy, pytest on 3.12/3.13) that the
  PyPI publish depends on; the tag must match the package version.

### Changed
- `pillow` moved to the `analyzers` extra; `adbutils` is no longer a direct dependency.
- The version is read from `geppetto/__init__.py` (single source).
- Install hints in import errors use the published name `geppetto-android[...]`.
- Removed the template `main.py`.

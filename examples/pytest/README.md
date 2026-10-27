# Example: Geppetto with pytest

Two tests against the Android **Settings** app (present on every device and emulator, and
language-independent because they check the activity, not the text).

```bash
pip install "geppetto-android" pytest-html     # or: uv add geppetto-android pytest-html
adb devices                                    # one device/emulator connected (or use --serial)

pytest                                         # uses the only connected device
pytest --serial emulator-5554 --geppetto-record --html=report.html --self-contained-html
```

`test_settings.py::test_wrong_screen_on_purpose` fails on purpose (it is marked `xfail`, so the run
stays green): open `report.html` to see its screenshot embedded, and the folder printed under
**geppetto artifacts** with `screenshot.png`, `window_dump.xml`, `logcat.txt` and, with
`--geppetto-record`, `screenrecord.mp4`. Remove the `xfail` marker to see a real failure.

`pyproject.toml` here shows the ini options; `conftest.py` shows how to customise the `Device`.

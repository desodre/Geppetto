# Example: Geppetto with pytest

This folder contains a login test and a small Android app with fixed demo credentials. The app
uses no network or account. Android Settings tests remain as a quick device check.

Build the app with JDK 17 or 21 and Android SDK Platform 36 installed, then install it on a device
or emulator (replace the serial as needed):

```bash
cd login_app
./gradlew :app:assembleDebug
adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
cd ..
```

Install the Python dependencies from this checkout and run from this `examples/pytest`
directory (after release, `pip install geppetto-android pytest pytest-html` works as well):

```bash
pip install -e ../.. pytest pytest-html
pytest test_login.py --serial emulator-5554 --html=report.html --self-contained-html
```

The login form accepts `demo` / `geppetto`. `test_login.py` enters these values, using
`log_text=False` for the password. To inspect failure artifacts, run `pytest test_settings.py`:
its intentional `xfail` keeps the run green and leaves a screenshot, UI dump, recent logcat and
video in `results/`. The screenshot is embedded in `report.html`; other files are linked there.
Use `--no-geppetto-record` when recording is unwanted.

`pyproject.toml` here shows the ini options; `conftest.py` shows how to customise the `Device`.

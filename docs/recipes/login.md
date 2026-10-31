# Login with pytest

Use the bundled offline login app: credentials `demo` / `geppetto`, no network account.
Build it with JDK 17 or 21 and SDK Platform 36; the emulator can run API 34.
From the repository root:

```bash
cd examples/pytest/login_app
./gradlew :app:assembleDebug
adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
cd ../../..
uv run pytest examples/pytest/test_login.py --serial emulator-5554
```

The example conftest starts/stops the app in a clean state and customizes the Device factory.
Wait for widgets rather than adding sleeps; password input suppresses logging.

```python
--8<-- "examples/pytest/test_login.py"
```

Run from this checkout for main-only features. The app's compile SDK requirement is independent
of the emulator's Android API level.

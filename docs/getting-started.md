# Getting started

Use Python 3.12 or 3.13, Android SDK platform tools (`adb`, optional `fastboot`) on PATH,
and an emulator or authorized ADB device. See the [support matrix](policies/versioning.md).

```bash
pip install geppetto-android pytest
geppetto devices
geppetto doctor -s emulator-5554
pytest --serial emulator-5554
```

Installing Geppetto registers the pytest plugin. The first `Device(serial)` connects
uiautomator2 and may install its agent. Select a serial explicitly when other devices
are connected. Never automate a personal device without its owner's authorization.

For the code in main, use a checkout:

```bash
git clone https://github.com/desodre/Geppetto.git
cd Geppetto
uv sync --frozen --group dev
```

## Optional features

```bash
pip install 'geppetto-android[analyzers]'  # image/video analysis
pip install 'geppetto-android[hardware]'  # Acroname USB hardware
pip install 'geppetto-android[cli]'       # QR pairing
pip install 'geppetto-android[all]'
```

Keep typed secrets out of logs with `device.input_text(value, log_text=False)`.
Pass caller data in lists when using low-level shell APIs: `adb.shell(["echo", value])`.
Plain shell strings are trusted constant command lines.

## Typed Python

The installed wheel includes `geppetto/py.typed`; mypy sees the public annotations.
This example is checked as part of documentation validation:

```python
--8<-- "examples/recipes/typing_example.py"
```

```bash
uv run mypy examples/recipes/typing_example.py
```

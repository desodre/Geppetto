# pytest integration

```python
def test_settings(device):
    device.open_app("com.android.settings")
    assert device.await_for_activity("com.android.settings", timeout=20)
```

`device` has function scope and reuses its session connection. `devices` returns all
selected devices in a session-scoped list; `device` alone captures only the first serial.
Override `geppetto_device_factory` in conftest to customize construction/output/logging.

```bash
pytest --serial emulator-5554
pytest --serial emulator-5554 --serial emulator-5556
pytest --all-devices
```

`GEPPETTO_SERIAL` accepts a comma-separated list. Without explicit selection, exactly one
connected ready device is selected; otherwise device tests skip with a reason.
CI checks readiness before running and rejects empty or entirely skipped integration.

Failure capture saves screenshot, hierarchy, recent logcat and video by default, including
xfail and fixture teardown failures. See the [artifact recipe](../recipes/failure-artifacts.md).
Options include `--geppetto-output DIR`, `--geppetto-artifacts on-failure|always|never`,
`--geppetto-logcat-seconds N` and `--no-geppetto-record`. Output and artifact mode also have
`geppetto_output` and `geppetto_artifacts` ini settings.
On older builds such as API 26, device timestamps have one-second precision, so the capture
boundary can include lines from the same second just before the test starts.

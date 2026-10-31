# Host-observed boot time

Measure from launching a dedicated AVD until Android reports `sys.boot_completed=1`.
Use an emulator you own; this recipe starts it and shuts it down afterwards.
It does not reboot a connected physical device.

```bash
geppetto emulator list
uv run python examples/recipes/boot_time.py My_AVD
```

```python
--8<-- "examples/recipes/boot_time.py"
```

The timeout bounds the emulator startup wait; failure raises `DeviceTimeoutError` or
`EmulatorError`. `time.monotonic()` measures elapsed host time, including emulator launch.
`-no-snapshot-load` avoids measuring a snapshot resume. This is not a camera-based timing
measurement or a guarantee that all apps are ready. The recipe uses the emulator startup
API instead of promising a total timeout for the older `Device.reboot` path.

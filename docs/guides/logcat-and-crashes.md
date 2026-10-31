# Logcat and crashes

These APIs are described by main; see the changelog for release availability.

```python
with device.logcat(tags=["Payments"], level="I") as log:
    device.click(device.await_widget(By.TEXT, "Pay"))
    log.expect("Payment OK", timeout=10)
    log.expect_no("Exception", within=2)

with device.watch_crashes("com.example"):
    device.open_app("com.example")
```

Streams begin at device time without clearing its log buffers. Filters combine package,
tag, level and regex; buffers are bounded. `expect` normally waits for a future line;
use `since_start=True` to search already buffered lines. `LogNotFoundError` includes context.
A watcher detects Java crashes, ANRs and native signals and raises `AppCrashedError` on
successful context exit when its watched package crashed.

```bash
pytest --serial emulator-5554 --geppetto-watch com.example
```

Use `geppetto_watch` in ini or `@pytest.mark.geppetto_watch("com.example")` as alternatives.
Only named packages are watched, avoiding unrelated system ANRs. A detected crash fails
a passing test and adds `crash.txt` to its artifacts. Logs arrive asynchronously; use
`settle()` before interpreting absence. See the [reference](../reference/recording-and-logcat.md).

# Inspector and code recorder

Inspector is available in main; check the changelog before using a published PyPI release.

```bash
geppetto inspect -s emulator-5554
```

Open the printed localhost URL. Hover highlights bounds; selecting a node shows attributes
and its recommended unique selector. Stable attributes win; position-based fallback is
marked fragile. Record mode executes taps/text/keys and generates Python to copy/download.

The server defaults to `127.0.0.1`; `--port 0` picks a free port. `--host` deliberately exposes
an interface that controls the device. Recorded text becomes part of the generated script;
avoid recording credentials. Prefer stable selectors when a UI changes between runs.

See the [Inspector API](../reference/inspector.md).

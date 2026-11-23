# Carlo backend

These APIs are described by main; see the changelog for release availability.

`Device` reads the UI hierarchy and the screen size from a **UI backend**. The default,
`uiautomator2`, installs the uiautomator2 agent on the device. The opt-in `carlo` backend
talks instead to Carlo, a small native agent that Geppetto pushes for the session and removes afterwards. Taps, text and keys go
through `adb shell` with either backend.

!!! warning "Current status"
    - **uiautomator2 stays the default.** Carlo is opt-in and nothing changes unless you
      select it.
    - Geppetto's side of the Carlo wire protocol (v1 framing, control client, session
      start/cleanup) is **tested on the host** against Carlo's shared protocol vectors and a
      fake agent. It is not yet exercised by Geppetto's emulator CI.
    - Carlo pins its supported device profile to **API 36**. API 34, which Geppetto's
      integration CI uses, is **still pending** on the Carlo side.
    - The Carlo backend covers the hierarchy dump and the screen size. `await_widget` polls
      the dump (Carlo has no server-side wait).

## Configure the binary

Build Carlo for the device's ABI and point Geppetto at the binary:

```bash
export GEPPETTO_CARLO_BINARY=/path/to/carlo
geppetto doctor   # the "carlo" line is OK when the file exists
```

`geppetto doctor` reports `INFO` while the variable is unset (only the `carlo` backend needs
it) and `WARN` when it points to a missing file.

## Use it from Python

```python
from geppetto import By, Device

with Device("emulator-5554", backend="carlo") as device:
    device.click(device.await_widget(By.TEXT, "Login"))
    print(device.screen_size)  # `wm size` (override first), swapped in landscape
```

`screen_size` follows the rotation: Geppetto reads `wm size` and the `SurfaceOrientation` line of
`dumpsys input` in one shell call and swaps width and height at 90° or 270°. When the rotation
cannot be read it falls back to the natural orientation from `wm size`.

Carlo exits after 30 s without a request. When a hierarchy dump then finds the connection
`closed` (or failing with `io`), the session is cleaned up, restarted once in a new directory
and the dump retried. Agent refusals (`unavailable`, `conflict`, `truncated`…) and `timeout`
are never retried. Pass `auto_reconnect=False` to `CarloSession` or `CarloBackend` to get the
error instead.

`carlo_binary="/path/to/carlo"` overrides `GEPPETTO_CARLO_BINARY`. Leaving the `with` block
(or calling `device.close()`) ends the session: Geppetto asks the agent to shut down, removes
the `adb forward`, stops the process and deletes the session directory. `close()` is
idempotent and never raises. For a lower-level session, use `CarloSession` from
`geppetto.core.carlo` (it also accepts the binary's expected `sha256`).

## Use it with pytest

```bash
pytest --serial emulator-5554 --geppetto-backend=carlo --geppetto-carlo-binary=/path/to/carlo
```

`GEPPETTO_BACKEND=carlo` and `GEPPETTO_CARLO_BINARY` work as well; command-line options win.
Devices are closed when the session ends, even if one close fails.

## What happens on the device

1. A private `0700` directory `/data/local/tmp/geppetto-carlo-<random>` is created and the
   binary is pushed into it.
2. `carlo serve` prints one JSON ready line with its socket (filesystem or abstract) and a
   session identifier.
3. The socket is forwarded with `adb forward tcp:0`, and the client authenticates with
   `hello`.

The session identifier is a bearer secret: it is only sent in `hello` and never logged.
Hierarchy XML is never logged either. Any failure while starting undoes what was already
done. Errors are `CarloError`; its `code` attribute carries a stable reason such as
`binary_missing`, `checksum_mismatch`, `timeout`, `unavailable` or `bad_magic`.

See the [reference](../reference/transport-and-services.md) for `geppetto.core.backend` and
`geppetto.core.carlo`.

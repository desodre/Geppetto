# AGENTS.md — working on Geppetto

Guide for humans and coding agents. Read it before changing code; keep it true when you change
architecture, rules or workflow (same PR).

## Purpose

Geppetto (`geppetto-android` on PyPI, `import geppetto`) is a typed Python framework for Android
automation. It wraps ADB, Fastboot and uiautomator2 behind one `Device` facade.

**Positioning:** *the Playwright of Android for device labs*. Not another app-testing tool
competing with Appium: Geppetto targets **device- and system-level QA** (OEM, carrier, hardware
labs), where you need the OS (Wi-Fi, lock screen, reboot, fastboot), several devices and lab
hardware (USB/power switches, cameras), with a modern Python API:

- Python-native, no server, `py.typed`, `mypy --strict` clean.
- Auto-waiting actions and retrying assertions (no `sleep` in user code).
- Failure artifacts for free through pytest (screenshot, UI dump, logcat, video).
- Hardware and multiple devices as first-class concepts.

The roadmap lives in the GitHub project **Geppetto Roadmap** (user `desodre`, project 10): one
parent issue per theme, sub-issues for the work, each with a **Done when**.

## Architecture

```
src/geppetto/
  __init__.py        public API, __version__ (single source), lazy optional imports
  device.py          Device: the facade users touch. Composes everything below.
  recording.py       ScreenRecording: background screenrecord (start / stop(save_to) / discard)
  logcat.py          LogcatStream: `logcat -T <device time>` read in a thread (never `logcat -c`),
                     filters, ring buffer, expect()/expect_no(), settle()
  crashes.py         CrashWatcher: Java/ANR/native crash parsing from every logcat line
  pytest_plugin.py   pytest11 entry point: options, device fixtures, failure artifacts, reports
  exceptions.py      GeppettoError and its subclasses (every error we raise)
  _logging.py        "geppetto.*" logger hierarchy + DeviceLogger (opt-in handlers)
  core/              transport: AdbClient, FastbootClient. Only place that spawns processes.
    adb.py           per-device adb (shell quoting, exec_out, spawn_shell, wait_for_boot)
    host.py          host-wide adb: devices -l, pair/connect, mdns, run_adb (AdbCommandError)
    emulator.py      SDK lookup, AVDs, start (waits for boot) / stop, snapshots
  doctor.py          environment checks; every non-OK Check carries a fix
  cli.py             `geppetto` console script (argparse, no extra deps; QR needs [cli])
  inspector/         `geppetto inspect`: selectors.py (recommend: unique-only, stable first),
                     recorder.py (actions → runnable script), server.py (stdlib http.server,
                     127.0.0.1 by default, one device lock), static/index.html (vanilla JS page)
  ui/                pure data: Bounds, Widget (keeps its lxml node), Children, WindowDump
  models/            enums: By, Direction, WifiSecurityType, CommonClasses
  services/          OS features on top of AdbClient: wifi, lockscreen, notification
  analyzers/         [extra "analyzers"] ScreenAnalyzer (Pillow, imagehash), VideoAnalyzer (OpenCV)
  hardware/          [extra "hardware"] AcronameController (brainstem)
tests/               unit tests, no device: subprocess.run is replaced by AdbRecorder
integration/         real device/emulator tests (skipped without one); CI runs them on an emulator
```

Layering (imports only go downwards):

```
Device ─► services ─► core (AdbClient/FastbootClient) ─► subprocess / adb binary
   │                     ▲
   └──► ui, models ──────┘ (ui/models never import core or Device)
analyzers, hardware: optional, imported lazily from geppetto/__init__.py
```

- **`core/`** is the only layer that runs processes. Everything else goes through `AdbClient`.
- **`ui/`** and **`models/`** are pure: no I/O, fully unit-testable with XML strings.
- **`services/`** receive an `AdbClient`, never a `Device` (no cycles).
- **`Device`** wires it together and owns the result folder (`<output>/<ts>_<serial>/`
  with `Images/Screenshots`, `Videos/Screenrecords`, `Logs`).
- **`pytest_plugin.py`** loads on every pytest run where the package is installed: keep its import
  cheap (`Device`/uiautomator2 are imported lazily) and never let an artifact failure change a test
  outcome. Its own tests use `pytester` with a fake `Device` from `geppetto_device_factory`; this
  repo's suite sets `geppetto_artifacts = "never"` so the capture does not touch the library tests.
- New big features get their own module/package (`locator/`, `cli/`…) depending on `Device`,
  never the other way round.

## Rules (obligations)

1. **Device shell commands with caller data are lists.** `adb shell` joins its arguments and the
   device `sh` parses them again; `shell=False` only protects the host. Use
   `adb.shell(["am", "force-stop", package])` (quoted by `core.adb.device_command`). A plain
   string is a *trusted, constant* command line only (`"getprop ro.serialno"`).
2. **Never log secrets.** PINs, passwords, Wi-Fi keys, tokens. Text input takes `log_text=False`.
3. **Errors are ours.** Raise a `GeppettoError` subclass (add one in `exceptions.py` if needed);
   don't leak `subprocess.CalledProcessError` from new public APIs without wrapping or documenting.
4. **Logging is library-friendly.** Get loggers under `geppetto.` (`DeviceLogger` or
   `logging.getLogger("geppetto.<area>")`). No `basicConfig`, no handlers on import, no `print`.
5. **Optional dependencies stay optional.** Import them inside the extra's module, raise
   `ImportError` with `pip install 'geppetto-android[<extra>]'`, expose through the lazy
   `__getattr__` in `__init__.py`, declare in `pyproject.toml` (extra **and** `all`).
6. **Public API is a contract.** Anything exported in `__all__` or documented in the README keeps
   working for at least one minor release after a deprecation (`DeprecationWarning` + CHANGELOG).
   Aliases are fine (`Direction.Up` → `Direction.UP`).
7. **Waits are bounded.** Every wait has a timeout, uses `time.monotonic()`, and raises
   `DeviceTimeoutError` (never loops forever, never `datetime` arithmetic).
8. **Types are strict.** `mypy --strict` must stay clean; no `Any` leaking out of public functions;
   `# type: ignore` only with the error code and a reason.
9. **Version has one source:** `__version__` in `src/geppetto/__init__.py`. Every user-visible
   change gets a line in `CHANGELOG.md` under the next version.
10. **No device-only code paths without a unit test.** Behaviour that builds adb commands is tested
    through `AdbRecorder` (`tests/conftest.py`); hardware/real-device checks are extra, not instead.

## Quality bar (a change is done when)

- `uv run ruff check src tests` and `uv run ruff format --check src tests` pass.
- `uv run mypy src` passes (strict).
- `uv run pytest` passes; new behaviour has tests (happy path, the failure/edge that motivated it).
- Public APIs have docstrings saying what they return and which `GeppettoError` they raise.
- README/docs updated when usage changes; CHANGELOG updated; AGENTS.md updated when rules or
  architecture change.
- CI is green. `ci.yml` (main, and called by the publish) runs lint, format, mypy and unit tests
  on Python 3.12/3.13. `dev.yml` (push/PR to `dev`) runs those unit tests on one runner and the
  `integration/` suite on an Android emulator (API 34, KVM, cached AVD) on another; failure
  artifacts are uploaded. Publishing to PyPI runs `ci.yml` first and requires the tag `vX.Y.Z` to
  equal `__version__`.
- Behaviour that only a real device proves (UI hierarchy, recording, the plugin's artifacts, CLI
  output) gets an `integration/` test too.

## Workflow

- **Issue first.** Work maps to an issue on the Geppetto Roadmap board (label `roadmap`); move it
  to *In Progress* when you start, reference it in commits, close it when merged.
- **Branches:** `feat/<slug>-<issue>`, `fix/<slug>-<issue>`, `docs/...`, `ci/...`, from `main`.
  PR into `main`; don't push to `main` directly.
- **Commits:** Conventional Commits in English (`feat(pytest): …`, `fix(adb): …`, `docs: …`,
  `ci: …`, `chore: …`, `test: …`), body explains *why*, `(#issue)` reference.
- Don't publish, tag or push without the maintainer asking.

## Commands

```bash
uv sync --group dev --all-extras        # dev environment (Python ≥ 3.12)
uv run pytest                           # unit tests, no device needed
uv run pytest integration --serial emulator-5554 --geppetto-artifacts=on-failure
uv run ruff check src tests && uv run ruff format src tests
uv run mypy src
uv build                                # wheel + sdist (version read from __init__.py)
```

If the machine has no Python 3.12, `UV_PYTHON=3.14 uv sync --group dev` works locally; CI covers
3.12/3.13.

## Gotchas

- **Crash watching is opt-in per package** (`--geppetto-watch`): CI emulators produce unrelated
  system ANRs; watching every app would make tests flaky.
- **Logcat lines arrive asynchronously**: call `LogcatStream.settle()` before deciding there was no
  line/crash (the plugin and `CrashWatcher.crashes()` do).
- **`adb shell` re-parses on the device** (see rule 1). `adb exec-out` has the same behaviour.
- **Recommended selectors must be unique in the dump**: `By.ID/TEXT/CONTENT_DESC` return the first
  match, so a shared value would record a tap on another element. `tests/test_inspector.py` checks
  that every recommended selector finds exactly its own node; keep that test passing.
- **`input text`**: a raw space ends the text; spaces must be `%s` (done by `Device.input_text`).
- **uiautomator2 XPath** is `d.xpath(expr)`, not `d(xpath=...)`.
- **lxml XPath** can return numbers/strings (`count(...)`): filter for `etree._Element`.
- **Never interpolate user text into XPath**; pass XPath variables (`$text`) instead.
- **`screenrecord`** is capped at 180 s by Android.
- **First `Device(serial)` installs the uiautomator2 agent** on the phone. Ask before running
  against someone's device.
- **Reboot** is not done when `adb wait-for-device` returns; wait for `sys.boot_completed`
  (`Device.wait_for_boot`).
- **A booting emulator** shows as `device` in `adb devices` while its shell still answers
  `error: closed`; keep retrying (`core.emulator._reach`).
- **Processes started by a coding agent's sandbox** may be killed when the command ends, even with
  `start_new_session`: drive an emulator start-to-stop in one command when validating.
- `Enum` members with equal values become aliases (that is how `Colors.ALMOST_BLUE` was lost).

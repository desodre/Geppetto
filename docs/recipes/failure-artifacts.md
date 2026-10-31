# Investigate failures

This intentional expected failure leaves artifacts while keeping the pytest run green.

```bash
uv run pytest examples/recipes/failure_artifacts.py --serial emulator-5554 \
  --geppetto-artifacts=on-failure --geppetto-output=results \
  --html=report.html --self-contained-html --junitxml=junit.xml
```

```python
--8<-- "examples/recipes/failure_artifacts.py"
```

| Artifact | Content |
| --- | --- |
| `screenshot.png` | Failure screen, embedded in pytest-html |
| `window_dump.xml` | UI hierarchy |
| `logcat.txt` | Recent test logs; device-wide buffers are not cleared |
| `screenrecord.mp4` | Video enabled by default; Android limits recording to 180 seconds |
| `crash.txt` | Watched crash details when crash monitoring is configured |

Folders live under `<output>/<run>_<serial>/Tests/<test id>/`. JUnit records
`geppetto_artifacts[<serial>]`; pytest-html links other artifacts. Only the screenshot is
embedded. Other links refer to local paths on the machine that ran the test; when sharing,
send the artifact files too and open them directly or update the links for their new location.

Use `--no-geppetto-record` to disable video, `--geppetto-logcat-seconds N` to change the
window, or `--geppetto-artifacts=always|never`. An artifact error produces an error file
when possible and does not replace the original test result. Captures can contain sensitive
screens/logs; use a demo app and review outputs before sharing.

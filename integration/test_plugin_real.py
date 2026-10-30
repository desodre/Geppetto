"""The pytest plugin against a real device: a failing test leaves real artifacts."""

import pathlib
import xml.etree.ElementTree as ET


def test_failure_artifacts_are_real(pytester, serial, tmp_path):
    pytester.makepyfile(
        "import time\n"
        "def test_falha(device):\n"
        "    device.adb.shell(['log', '-t', 'GeppettoTest', 'geppetto-issue-7'])\n"
        "    time.sleep(1)\n"
        "    assert False\n"
    )
    result = pytester.runpytest(
        "--serial",
        serial,
        "--geppetto-output",
        str(tmp_path),
        "--junitxml=junit.xml",
        "--html=report.html",
        "--self-contained-html",
    )
    result.assert_outcomes(failed=1)
    props = {
        p.get("name"): p.get("value")
        for p in ET.parse(pytester.path / "junit.xml").iter("property")
    }
    pasta = pathlib.Path(props[f"geppetto_artifacts[{serial}]"])
    assert (pasta / "screenshot.png").read_bytes()[:4] == b"\x89PNG"
    assert "<hierarchy" in (pasta / "window_dump.xml").read_text()
    assert "geppetto-issue-7" in (pasta / "logcat.txt").read_text()
    assert (pasta / "screenrecord.mp4").read_bytes()[4:8] == b"ftyp"
    html = (pytester.path / "report.html").read_text()
    assert f"{serial} screenshot" in html
    assert f"{serial} screenrecord.mp4" in html

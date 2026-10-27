"""The pytest plugin against a real device: a failing test leaves real artifacts."""

import pathlib
import xml.etree.ElementTree as ET


def test_failure_artifacts_are_real(pytester, serial, tmp_path):
    pytester.makepyfile("def test_falha(device):\n    assert False\n")
    result = pytester.runpytest(
        "--serial", serial, "--geppetto-output", str(tmp_path), "--junitxml=junit.xml"
    )
    result.assert_outcomes(failed=1)
    props = {
        p.get("name"): p.get("value")
        for p in ET.parse(pytester.path / "junit.xml").iter("property")
    }
    pasta = pathlib.Path(props[f"geppetto_artifacts[{serial}]"])
    assert (pasta / "screenshot.png").read_bytes()[:4] == b"\x89PNG"
    assert "<hierarchy" in (pasta / "window_dump.xml").read_text()
    assert (pasta / "logcat.txt").exists()

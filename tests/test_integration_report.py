from xml.etree import ElementTree

import pytest

from scripts.check_integration import executed_tests


@pytest.mark.parametrize(
    ("cases", "expected"),
    [
        ('<testcase name="passed"/>', 1),
        ('<testcase><failure message="original failure"/></testcase>', 1),
        ("<testcase/><testcase><skipped/></testcase><testcase><error/></testcase>", 2),
    ],
)
def test_counts_executed_cases_without_overriding_pytest_failures(tmp_path, cases, expected):
    report = tmp_path / "junit.xml"
    report.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
    assert executed_tests(report) == expected


@pytest.mark.parametrize("cases", ["", '<testcase name="missing device"><skipped/></testcase>'])
def test_empty_or_all_skipped_runs_are_rejected(tmp_path, cases):
    report = tmp_path / "junit.xml"
    report.write_text(f"<testsuite>{cases}</testsuite>")
    with pytest.raises(ValueError, match="no executed tests"):
        executed_tests(report)


def test_missing_or_malformed_reports_are_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        executed_tests(tmp_path / "missing.xml")
    report = tmp_path / "broken.xml"
    report.write_text("<testsuite")
    with pytest.raises(ElementTree.ParseError):
        executed_tests(report)

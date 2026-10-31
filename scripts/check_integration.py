"""Reject empty or entirely skipped JUnit runs; pytest owns individual test failures."""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.etree import ElementTree


def executed_tests(report: Path) -> int:
    """Return non-skipped test cases, rejecting unusable reports."""
    root = ElementTree.parse(report).getroot()
    executed = sum(case.find("skipped") is None for case in root.iter("testcase"))
    if not executed:
        raise ValueError("Integration run contains no executed tests (empty or all skipped)")
    return executed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        count = executed_tests(args.report)
    except (OSError, ElementTree.ParseError, ValueError) as error:
        parser.exit(1, f"Integration report rejected: {error}\n")
    print(f"Integration report: {count} test case(s) executed")


if __name__ == "__main__":
    main()

"""``expect(locator)``: assertions that retry until they hold or the timeout expires.

Every assertion re-dumps the hierarchy on each attempt and, on timeout, raises
:class:`~geppetto.exceptions.ExpectationError` (also an ``AssertionError``) whose message
carries the expectation and the last observed state.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable

from ..exceptions import ExpectationError
from ..ui.widget import Widget
from .locator import Locator, describe, is_visible

Predicate = Callable[[list[Widget]], bool]


def expect(
    locator: Locator, *, timeout: float | None = None, poll: float = 0.25
) -> LocatorAssertions:
    """Start an assertion on *locator*.

    *timeout* (seconds) defaults to the device's ``default_timeout``; *poll* is the pause
    between two attempts.
    """
    return LocatorAssertions(locator, timeout, poll)


class LocatorAssertions:
    """Retrying assertions on a :class:`Locator`; negate with ``.not_``."""

    def __init__(
        self,
        locator: Locator,
        timeout: float | None,
        poll: float,
        negate: bool = False,
    ) -> None:
        self._locator = locator
        self._timeout = timeout
        self._poll = poll
        self._negate = negate

    @property
    def not_(self) -> LocatorAssertions:
        """The opposite expectation: ``expect(loc).not_.to_be_visible()``."""
        return LocatorAssertions(self._locator, self._timeout, self._poll, not self._negate)

    # ── State ────────────────────────────────────────────────────────

    def to_be_visible(self, timeout: float | None = None) -> None:
        """At least one match with a non-empty box on screen."""
        self._check(lambda ws: bool(ws) and is_visible(ws[0]), "visible", timeout)

    def to_be_hidden(self, timeout: float | None = None) -> None:
        """No match, or a match without a box on screen."""
        self._check(lambda ws: not ws or not is_visible(ws[0]), "hidden", timeout)

    def to_be_enabled(self, timeout: float | None = None) -> None:
        self._check(lambda ws: bool(ws) and ws[0].enabled, "enabled", timeout)

    def to_be_disabled(self, timeout: float | None = None) -> None:
        self._check(lambda ws: bool(ws) and not ws[0].enabled, "disabled", timeout)

    def to_be_checked(self, checked: bool = True, timeout: float | None = None) -> None:
        state = "checked" if checked else "unchecked"
        self._check(lambda ws: bool(ws) and ws[0].checked is checked, state, timeout)

    def to_be_selected(self, selected: bool = True, timeout: float | None = None) -> None:
        state = "selected" if selected else "unselected"
        self._check(lambda ws: bool(ws) and ws[0].selected is selected, state, timeout)

    def to_be_focused(self, timeout: float | None = None) -> None:
        self._check(lambda ws: bool(ws) and ws[0].focused, "focused", timeout)

    # ── Content ──────────────────────────────────────────────────────

    def to_have_text(
        self,
        expected: str | re.Pattern[str],
        *,
        exact: bool = True,
        timeout: float | None = None,
    ) -> None:
        """The first match's ``text`` equals *expected* (after stripping), contains it with
        ``exact=False``, or matches the regex."""
        matcher, label = _text_matcher(expected, exact)
        self._check(
            lambda ws: bool(ws) and matcher(ws[0].text),
            f"text {label}",
            timeout,
            observed=lambda ws: f"text {ws[0].text!r}" if ws else "0 matches",
        )

    def to_contain_text(self, expected: str, timeout: float | None = None) -> None:
        """Shortcut for ``to_have_text(expected, exact=False)``."""
        self.to_have_text(expected, exact=False, timeout=timeout)

    def to_have_content_desc(
        self,
        expected: str | re.Pattern[str],
        *,
        exact: bool = True,
        timeout: float | None = None,
    ) -> None:
        matcher, label = _text_matcher(expected, exact)
        self._check(
            lambda ws: bool(ws) and matcher(ws[0].content_desc),
            f"content-desc {label}",
            timeout,
            observed=lambda ws: f"content-desc {ws[0].content_desc!r}" if ws else "0 matches",
        )

    def to_have_count(self, count: int, timeout: float | None = None) -> None:
        """Exactly *count* matches."""
        self._check(
            lambda ws: len(ws) == count,
            f"{count} match{'es' if count != 1 else ''}",
            timeout,
            observed=lambda ws: f"{len(ws)} match{'es' if len(ws) != 1 else ''}",
        )

    # ── Engine ───────────────────────────────────────────────────────

    def _check(
        self,
        holds: Predicate,
        expectation: str,
        timeout: float | None,
        observed: Callable[[list[Widget]], str] = describe,
    ) -> None:
        if timeout is None:
            timeout = self._timeout
        if timeout is None:
            timeout = self._locator._device.default_timeout
        deadline = time.monotonic() + timeout
        while True:
            widgets = self._locator.all()
            if holds(widgets) is not self._negate:
                return
            if time.monotonic() >= deadline:
                wording = "not to be" if self._negate else "to be"
                raise ExpectationError(
                    f"Expected {self._locator} {wording} {expectation} "
                    f"(waited {timeout:g}s); last seen: {observed(widgets)}"
                )
            time.sleep(self._poll)


def _text_matcher(
    expected: str | re.Pattern[str], exact: bool
) -> tuple[Callable[[str], bool], str]:
    if isinstance(expected, re.Pattern):
        pattern = expected
        return (lambda text: pattern.search(text) is not None), f"matching /{pattern.pattern}/"
    if exact:
        return (lambda text: text.strip() == expected.strip()), repr(expected)
    needle = expected.lower()
    return (lambda text: needle in text.lower()), f"containing {expected!r}"

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

    Args:
        locator: The locator to check.
        timeout: Seconds every assertion retries; defaults to the device's
            ``default_timeout``.
        poll: Seconds between two attempts.

    Returns:
        The assertions bound to *locator*.
    """
    return LocatorAssertions(locator, timeout, poll)


class LocatorAssertions:
    """Retrying assertions on a :class:`Locator`; negate with ``.not_``.

    State and content assertions (``to_be_enabled``, ``to_have_text``…) are about an existing
    element: when nothing matches they fail, negated or not. Only ``to_be_visible``,
    ``to_be_hidden`` and ``to_have_count`` treat "no match" as a state.
    """

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
        """Assert that the first match has a non-empty box on screen.

        Args:
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout.
        """
        self._check(lambda ws: bool(ws) and is_visible(ws[0]), "visible", timeout)

    def to_be_hidden(self, timeout: float | None = None) -> None:
        """Assert that nothing matches, or that the first match has no box on screen.

        Args:
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout.
        """
        self._check(lambda ws: not ws or not is_visible(ws[0]), "hidden", timeout)

    def to_be_enabled(self, timeout: float | None = None) -> None:
        """Assert that the first match is enabled.

        Args:
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout, including
                when nothing matches.
        """
        self._check(lambda ws: bool(ws) and ws[0].enabled, "enabled", timeout, require_match=True)

    def to_be_disabled(self, timeout: float | None = None) -> None:
        """Assert that the first match is disabled.

        Args:
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout, including
                when nothing matches.
        """
        self._check(
            lambda ws: bool(ws) and not ws[0].enabled, "disabled", timeout, require_match=True
        )

    def to_be_checked(self, checked: bool = True, timeout: float | None = None) -> None:
        """Assert that the first match is checked (or unchecked with ``checked=False``).

        Args:
            checked: The expected checked state.
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout, including
                when nothing matches.
        """
        state = "checked" if checked else "unchecked"
        self._check(
            lambda ws: bool(ws) and ws[0].checked is checked, state, timeout, require_match=True
        )

    def to_be_selected(self, selected: bool = True, timeout: float | None = None) -> None:
        """Assert that the first match is selected (or unselected with ``selected=False``).

        Args:
            selected: The expected selected state.
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout, including
                when nothing matches.
        """
        state = "selected" if selected else "unselected"
        self._check(
            lambda ws: bool(ws) and ws[0].selected is selected, state, timeout, require_match=True
        )

    def to_be_focused(self, timeout: float | None = None) -> None:
        """Assert that the first match has the input focus.

        Args:
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout, including
                when nothing matches.
        """
        self._check(lambda ws: bool(ws) and ws[0].focused, "focused", timeout, require_match=True)

    # ── Content ──────────────────────────────────────────────────────

    def to_have_text(
        self,
        expected: str | re.Pattern[str],
        *,
        exact: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Assert the ``text`` of the first match.

        Args:
            expected: Text compared after stripping, or a compiled regex (searched).
            exact: ``False`` accepts a case-insensitive substring.
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout, including
                when nothing matches.
        """
        matcher, label = _text_matcher(expected, exact)
        self._check(
            lambda ws: bool(ws) and matcher(ws[0].text),
            f"text {label}",
            timeout,
            observed=lambda ws: f"text {ws[0].text!r}" if ws else "0 matches",
            require_match=True,
        )

    def to_contain_text(self, expected: str, timeout: float | None = None) -> None:
        """Assert that the first match's ``text`` contains *expected* (case-insensitive).

        Shortcut for ``to_have_text(expected, exact=False)``.

        Args:
            expected: Substring to look for.
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout, including
                when nothing matches.
        """
        self.to_have_text(expected, exact=False, timeout=timeout)

    def to_have_content_desc(
        self,
        expected: str | re.Pattern[str],
        *,
        exact: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Assert the ``content-desc`` of the first match.

        Args:
            expected: Value compared after stripping, or a compiled regex (searched).
            exact: ``False`` accepts a case-insensitive substring.
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout, including
                when nothing matches.
        """
        matcher, label = _text_matcher(expected, exact)
        self._check(
            lambda ws: bool(ws) and matcher(ws[0].content_desc),
            f"content-desc {label}",
            timeout,
            observed=lambda ws: f"content-desc {ws[0].content_desc!r}" if ws else "0 matches",
            require_match=True,
        )

    def to_have_count(self, count: int, timeout: float | None = None) -> None:
        """Assert that exactly *count* widgets match.

        Args:
            count: Expected number of matches.
            timeout: Seconds to retry; defaults to the ``expect()`` timeout.

        Raises:
            ExpectationError: When the expectation still fails at the timeout.
        """
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
        require_match: bool = False,
    ) -> None:
        if timeout is None:
            timeout = self._timeout
        if timeout is None:
            timeout = self._locator._device.default_timeout
        deadline = time.monotonic() + timeout
        while True:
            widgets = self._locator.all()
            # With require_match, "no element" satisfies neither the assertion nor its negation.
            if (widgets or not require_match) and holds(widgets) is not self._negate:
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

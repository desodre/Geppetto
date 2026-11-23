"""``Locator``: a lazy, chainable selector whose actions wait for the element.

Nothing touches the device until an action or a read is called; then the hierarchy is dumped
and polled until the element is in the state the action needs (bounded by
``Device.default_timeout``). Actions go through the ``Device`` methods, so command quoting and
logging rules are inherited.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..exceptions import DeviceTimeoutError
from ..models.by import By
from ..ui.widget import Widget
from ..ui.window_dump import WindowDump
from .query import Filter, Find, Has, Match, Nth, Query, Relative, Side, Value, Within

if TYPE_CHECKING:
    from ..device import Device

#: Seconds between two hierarchy dumps while waiting.
POLL_INTERVAL = 0.25
#: ``KEYCODE_MOVE_END`` and ``KEYCODE_DEL``, used by :meth:`Locator.fill`.
_MOVE_END, _DEL = 123, 67


def is_visible(widget: Widget) -> bool:
    """A widget with a non-empty box on screen."""
    return widget.bounds is not None and widget.bounds.width > 0 and widget.bounds.height > 0


def describe(widgets: list[Widget]) -> str:
    """Short account of what a resolution found, for timeout and assertion messages."""
    if not widgets:
        return "0 matches"
    first = widgets[0]
    state = (
        f"{first.class_name or 'node'} text={first.text!r} enabled={first.enabled} "
        f"checked={first.checked} bounds={first.bounds}"
    )
    return state if len(widgets) == 1 else f"{len(widgets)} matches, first: {state}"


class Locator:
    """A selector bound to a :class:`~geppetto.Device`, resolved on every use.

    Build one with ``device.get(By.TEXT, "Login")`` and refine it by chaining; every method that
    refines returns a new ``Locator`` (the original is unchanged).

    Example::

        device.get(By.ID, "com.app:id/login").click()
        email = device.get(By.TEXT, "Email")
        device.get(By.CLASS, "android.widget.EditText").below(email).fill("me@example.com")
        expect(device.get(By.ID, "com.app:id/error")).to_have_text("Invalid password")
    """

    def __init__(self, device: Device, query: Query) -> None:
        self._device = device
        self._query = query

    # ── Refinement (no I/O) ─────────────────────────────────────────

    def get(self, by: By, value: Value, *, exact: bool = True) -> Locator:
        """Descendants of this locator's matches that satisfy *by*/*value*."""
        return self._then(Find(Match(by, value, exact)))

    def filter(
        self,
        by: By | None = None,
        value: Value | None = None,
        *,
        exact: bool = True,
        has: Locator | None = None,
    ) -> Locator:
        """Narrow the matches: the same node must also satisfy *by*/*value*, and/or contain a
        descendant matched by *has*."""
        if (by is None) != (value is None):
            raise TypeError("filter() needs both `by` and `value`, or neither")
        if by is None and has is None:
            raise TypeError("filter() needs `by`/`value` or `has`")
        result = self
        if by is not None and value is not None:
            result = result._then(Filter(Match(by, value, exact)))
        if has is not None:
            result = result._then(Has(has._query))
        return result

    def within(self, other: Locator) -> Locator:
        """Only matches inside the first match of *other*."""
        return self._then(Within(other._query))

    def below(self, other: Locator) -> Locator:
        """Matches under *other* on screen, closest first."""
        return self._then(Relative(Side.BELOW, other._query))

    def above(self, other: Locator) -> Locator:
        """Matches over *other* on screen, closest first."""
        return self._then(Relative(Side.ABOVE, other._query))

    def right_of(self, other: Locator) -> Locator:
        """Matches to the right of *other* on screen, closest first."""
        return self._then(Relative(Side.RIGHT_OF, other._query))

    def left_of(self, other: Locator) -> Locator:
        """Matches to the left of *other* on screen, closest first."""
        return self._then(Relative(Side.LEFT_OF, other._query))

    def nth(self, index: int) -> Locator:
        """The match at *index* (``-1`` is the last)."""
        return self._then(Nth(index))

    @property
    def first(self) -> Locator:
        return self.nth(0)

    @property
    def last(self) -> Locator:
        return self.nth(-1)

    def _then(self, step: Find | Filter | Has | Within | Relative | Nth) -> Locator:
        return Locator(self._device, self._query.then(step))

    @property
    def query(self) -> Query:
        return self._query

    # ── Resolution ───────────────────────────────────────────────────

    def all(self) -> list[Widget]:
        """Every match in the current hierarchy, right now (no waiting)."""
        return self._resolve()[1]

    def _resolve(self) -> tuple[WindowDump, list[Widget]]:
        dump = self._device.get_window_dump()
        return dump, [Widget.from_xml_node(node) for node in self._query.resolve(dump.root)]

    def count(self) -> int:
        """How many widgets match right now."""
        return len(self.all())

    def is_visible(self) -> bool:
        """Whether the first match exists and has a box on screen (no waiting)."""
        widgets = self.all()
        return bool(widgets) and is_visible(widgets[0])

    def is_enabled(self) -> bool:
        widgets = self.all()
        return bool(widgets) and widgets[0].enabled

    def is_checked(self) -> bool:
        widgets = self.all()
        return bool(widgets) and widgets[0].checked

    def widget(self, timeout: float | None = None) -> Widget:
        """Wait for the first match and return it, with its children filled in.

        Raises:
            DeviceTimeoutError: When nothing matches within *timeout* seconds.
        """
        dump, widgets = self._wait(lambda ws: bool(ws), "present", timeout)
        dump.set_children(widgets[0])
        return widgets[0]

    @property
    def text(self) -> str:
        """The ``text`` of the first match (waits for it)."""
        return self.widget().text

    def wait_for(self, state: str = "visible", timeout: float | None = None) -> Widget | None:
        """Wait until the locator is ``"visible"``, ``"hidden"``, ``"enabled"`` or
        ``"attached"`` (present). Returns the widget, or ``None`` for ``"hidden"``.

        Raises:
            DeviceTimeoutError: When the state is not reached in time.
            ValueError: For an unknown *state*.
        """
        checks: dict[str, Callable[[list[Widget]], bool]] = {
            "attached": lambda ws: bool(ws),
            "visible": lambda ws: bool(ws) and is_visible(ws[0]),
            "hidden": lambda ws: not ws or not is_visible(ws[0]),
            "enabled": lambda ws: bool(ws) and is_visible(ws[0]) and ws[0].enabled,
        }
        if state not in checks:
            raise ValueError(f"unknown state {state!r}; use one of {', '.join(checks)}")
        _, widgets = self._wait(checks[state], state, timeout)
        return widgets[0] if widgets and state != "hidden" else None

    # ── Actions (auto-waiting) ───────────────────────────────────────

    def click(self, timeout: float | None = None) -> None:
        """Tap the center of the element once it is visible and enabled."""
        self._device.click(self._actionable(timeout))

    def long_press(self, duration: float = 1.0, timeout: float | None = None) -> None:
        """Press the center of the element for *duration* seconds."""
        widget = self._actionable(timeout)
        assert widget.bounds is not None
        center = widget.bounds.center
        self._device.swipe(center, center, duration * 1000)

    def type_text(self, text: str, *, log_text: bool = True, timeout: float | None = None) -> None:
        """Tap the element, then type *text* after what is already there."""
        self.click(timeout)
        self._device.input_text(text, log_text=log_text)

    def fill(self, text: str, *, log_text: bool = True, timeout: float | None = None) -> None:
        """Tap the field, delete its current text and type *text*.

        Pass ``log_text=False`` for passwords: the text stays out of the logs.
        """
        widget = self._actionable(timeout)
        self._device.click(widget)
        if widget.text:
            self._device.key_event(_MOVE_END)
            self._device.adb.shell(["input", "keyevent", *([str(_DEL)] * len(widget.text))])
        self._device.input_text(text, log_text=log_text)

    def swipe_to(
        self,
        target: Locator | tuple[float, float],
        duration: float = 1.0,
        timeout: float | None = None,
    ) -> None:
        """Swipe from the center of this element to *target* (another locator or ``(x, y)``)."""
        source = self._actionable(timeout)
        assert source.bounds is not None
        if isinstance(target, Locator):
            destination = target._actionable(timeout)
            assert destination.bounds is not None
            end = destination.bounds.center
        else:
            end = target
        self._device.swipe(source.bounds.center, end, duration * 1000)

    # ── Internals ────────────────────────────────────────────────────

    def _actionable(self, timeout: float | None) -> Widget:
        def ready(widgets: list[Widget]) -> bool:
            return bool(widgets) and is_visible(widgets[0]) and widgets[0].enabled

        return self._wait(ready, "visible and enabled", timeout)[1][0]

    def _wait(
        self,
        ready: Callable[[list[Widget]], bool],
        state: str,
        timeout: float | None,
    ) -> tuple[WindowDump, list[Widget]]:
        limit = self._device.default_timeout if timeout is None else timeout
        deadline = time.monotonic() + limit
        while True:
            dump, widgets = self._resolve()
            if ready(widgets):
                return dump, widgets
            if time.monotonic() >= deadline:
                raise DeviceTimeoutError(
                    f"Timeout after {limit:g}s waiting for {self} to be {state}; "
                    f"last seen: {describe(widgets)}"
                )
            time.sleep(POLL_INTERVAL)

    def __str__(self) -> str:
        return f"device.{self._query}"

    def __repr__(self) -> str:
        return f"Locator({self})"

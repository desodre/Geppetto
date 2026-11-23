"""Pure resolution of a locator query against a UI hierarchy dump.

A :class:`Query` is an immutable chain of steps. :meth:`Query.resolve` applies them to the
``lxml`` root of a :class:`~geppetto.ui.window_dump.WindowDump` and returns the matching
``<node>`` elements in document order (or by distance, after a relative step). No I/O happens
here, which is what makes selectors testable with XML strings alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from lxml import etree

from ..models.by import By
from ..ui.bounds import Bounds

#: Hierarchy attribute behind each :class:`By` strategy (``By.XPATH`` is evaluated as such).
ATTRIBUTES: dict[By, str] = {
    By.TEXT: "text",
    By.ID: "resource-id",
    By.CLASS: "class",
    By.CONTENT_DESC: "content-desc",
}

Value: TypeAlias = str | re.Pattern[str]
Node: TypeAlias = etree._Element


class Side(Enum):
    """Where a candidate must be relative to the anchor of a relative step."""

    BELOW = "below"
    ABOVE = "above"
    RIGHT_OF = "right_of"
    LEFT_OF = "left_of"


@dataclass(frozen=True)
class Match:
    """One ``By``/value test on a node."""

    by: By
    value: Value
    exact: bool = True

    def __post_init__(self) -> None:
        if self.by is By.WIDGET:
            raise ValueError("By.WIDGET is not a search strategy")
        if self.by is By.XPATH and not isinstance(self.value, str):
            raise TypeError("By.XPATH takes a string expression, not a regex")
        if not isinstance(self.value, str | re.Pattern):
            raise TypeError(f"value must be a str or a compiled regex, not {type(self.value)!r}")

    def test(self, node: Node) -> bool:
        """Whether *node* satisfies this match (not for ``By.XPATH``, see :func:`_find`)."""
        attr = node.get(ATTRIBUTES[self.by], "")
        if isinstance(self.value, re.Pattern):
            return self.value.search(attr) is not None
        if self.exact:
            return bool(attr == self.value)
        return self.value.lower() in attr.lower()

    def __str__(self) -> str:
        value = (
            f"/{self.value.pattern}/" if isinstance(self.value, re.Pattern) else repr(self.value)
        )
        exact = "" if self.exact or isinstance(self.value, re.Pattern) else ", exact=False"
        return f"By.{self.by.name}, {value}{exact}"


@dataclass(frozen=True)
class Find:
    """Search nodes (the whole dump, or the descendants of the current candidates)."""

    match: Match

    def __str__(self) -> str:
        return f"get({self.match})"


@dataclass(frozen=True)
class Filter:
    """Keep the candidates that satisfy *match*."""

    match: Match

    def __str__(self) -> str:
        return f"filter({self.match})"


@dataclass(frozen=True)
class Has:
    """Keep the candidates that contain a match of *query* among their descendants."""

    query: Query

    def __str__(self) -> str:
        return f"filter(has={self.query})"


@dataclass(frozen=True)
class Within:
    """Keep the candidates that are descendants of the first match of *query*."""

    query: Query

    def __str__(self) -> str:
        return f"within({self.query})"


@dataclass(frozen=True)
class Relative:
    """Keep the candidates on *side* of the first match of *query*, closest first."""

    side: Side
    query: Query

    def __str__(self) -> str:
        return f"{self.side.value}({self.query})"


@dataclass(frozen=True)
class Nth:
    """Keep only the candidate at *index* (negative counts from the end)."""

    index: int

    def __str__(self) -> str:
        return f"nth({self.index})"


Step = Find | Filter | Has | Within | Relative | Nth


@dataclass(frozen=True)
class Query:
    """An immutable chain of steps; every ``with_*`` method returns a new query."""

    steps: tuple[Step, ...] = ()

    def then(self, step: Step) -> Query:
        return Query((*self.steps, step))

    def resolve(self, root: Node, scope: Node | None = None) -> list[Node]:
        """The nodes matching this query in *root*.

        With *scope*, the first search is restricted to the descendants of that node (used by
        :class:`Has`). The result keeps document order unless a :class:`Relative` step sorted it.
        """
        candidates: list[Node] | None = None
        for step in self.steps:
            match step:
                case Find(match):
                    bases = [scope] if candidates is None and scope is not None else candidates
                    candidates = _find(root, bases, match)
                case Filter(match):
                    current = _all(root, scope) if candidates is None else candidates
                    candidates = _filter(root, current, match)
                case Has(query):
                    current = _all(root, scope) if candidates is None else candidates
                    candidates = [n for n in current if query.resolve(root, scope=n)]
                case Within(query):
                    current = _all(root, scope) if candidates is None else candidates
                    anchors = query.resolve(root)
                    if not anchors:
                        candidates = []
                    else:
                        anchor = anchors[0]
                        candidates = [n for n in current if anchor in n.iterancestors()]
                case Relative(side, query):
                    current = _all(root, scope) if candidates is None else candidates
                    anchors = query.resolve(root)
                    candidates = _relative(current, anchors[0], side) if anchors else []
                case Nth(index):
                    current = _all(root, scope) if candidates is None else candidates
                    try:
                        candidates = [current[index]]
                    except IndexError:
                        candidates = []
        return _all(root, scope) if candidates is None else candidates

    def __str__(self) -> str:
        return ".".join(str(step) for step in self.steps) or "get()"


# ── Step helpers ─────────────────────────────────────────────────────


def _all(root: Node, scope: Node | None) -> list[Node]:
    base = root if scope is None else scope
    return list(base.iterdescendants("node")) if scope is not None else list(base.iter("node"))


def _xpath_nodes(base: Node, expression: str) -> list[Node]:
    result = base.xpath(expression)
    # `count(//node)` returns a number: not an element, so not a match.
    return [n for n in result if isinstance(n, etree._Element)] if isinstance(result, list) else []


def _find(root: Node, bases: list[Node] | None, match: Match) -> list[Node]:
    if bases is None:
        if match.by is By.XPATH:
            assert isinstance(match.value, str)
            return _xpath_nodes(root, match.value)
        return [n for n in root.iter("node") if match.test(n)]

    found: list[Node] = []
    for base in bases:
        if match.by is By.XPATH:
            assert isinstance(match.value, str)
            expression = match.value
            if expression.startswith("//"):
                expression = "." + expression  # relative to the candidate, not the document
            # `(//node)[1]` or `/hierarchy//node` stay absolute: keep only real descendants.
            nodes: Iterable[Node] = [
                n for n in _xpath_nodes(base, expression) if base in n.iterancestors()
            ]
        else:
            nodes = (n for n in base.iterdescendants("node") if match.test(n))
        found.extend(nodes)
    return _unique(found)


def _filter(root: Node, candidates: list[Node], match: Match) -> list[Node]:
    if match.by is By.XPATH:
        assert isinstance(match.value, str)
        allowed = set(map(id, _xpath_nodes(root, match.value)))
        return [n for n in candidates if id(n) in allowed]
    return [n for n in candidates if match.test(n)]


def _unique(nodes: Iterable[Node]) -> list[Node]:
    seen: set[int] = set()
    result: list[Node] = []
    for node in nodes:
        if id(node) not in seen:
            seen.add(id(node))
            result.append(node)
    return result


def _bounds(node: Node) -> Bounds | None:
    raw = node.get("bounds") or ""
    try:
        return Bounds(raw) if raw else None
    except ValueError:
        return None


def _relative(candidates: list[Node], anchor: Node, side: Side) -> list[Node]:
    base = _bounds(anchor)
    if base is None:
        return []
    ranked: list[tuple[float, float, Node]] = []
    for node in candidates:
        if node is anchor:
            continue
        box = _bounds(node)
        if box is None:
            continue
        gap, drift = _distance(box, base, side)
        if gap is not None:
            ranked.append((gap, drift, node))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [node for _, _, node in ranked]


def _distance(box: Bounds, base: Bounds, side: Side) -> tuple[float | None, float]:
    """``(gap along the side's axis, offset on the other axis)``; gap ``None`` when not on that
    side."""
    (cx, cy), (bx, by) = box.center, base.center
    match side:
        case Side.BELOW:
            return (box.y1 - base.y2, abs(cx - bx)) if box.y1 >= base.y2 else (None, 0)
        case Side.ABOVE:
            return (base.y1 - box.y2, abs(cx - bx)) if box.y2 <= base.y1 else (None, 0)
        case Side.RIGHT_OF:
            return (box.x1 - base.x2, abs(cy - by)) if box.x1 >= base.x2 else (None, 0)
        case Side.LEFT_OF:
            return (base.x1 - box.x2, abs(cy - by)) if box.x2 <= base.x1 else (None, 0)

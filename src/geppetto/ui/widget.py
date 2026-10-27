from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lxml import etree

from .bounds import Bounds

if TYPE_CHECKING:
    from .children import Children


def _flag(attrs: Mapping[str, str], name: str) -> bool:
    return attrs.get(name, "false").lower() == "true"


@dataclass(eq=False)
class Widget:
    """Represents a single Android UI element extracted from a window hierarchy dump."""

    index: str = ""
    text: str = ""
    id: str = ""
    class_name: str = ""
    package: str = ""
    content_desc: str = ""
    checkable: bool = False
    checked: bool = False
    clickable: bool = False
    enabled: bool = False
    focusable: bool = False
    focused: bool = False
    scrollable: bool = False
    long_clickable: bool = False
    is_password: bool = False
    selected: bool = False
    bounds: Bounds | None = None
    drawing_order: str = ""
    children: Children | None = field(default=None, repr=False)
    #: The XML node this widget came from (``None`` when built from a dict).
    node: etree._Element | None = field(default=None, repr=False)

    # ── Factory Methods ──────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> Widget:
        """Build from the attributes of a hierarchy ``<node>`` (``resource-id``, ``bounds``…).

        A missing or empty ``bounds`` gives ``bounds=None`` instead of an error.
        """
        bounds = data.get("bounds") or None
        return cls(
            index=data.get("index", ""),
            text=data.get("text", ""),
            id=data.get("resource-id", ""),
            class_name=data.get("class", ""),
            package=data.get("package", ""),
            content_desc=data.get("content-desc", ""),
            checkable=_flag(data, "checkable"),
            checked=_flag(data, "checked"),
            clickable=_flag(data, "clickable"),
            enabled=_flag(data, "enabled"),
            focusable=_flag(data, "focusable"),
            focused=_flag(data, "focused"),
            scrollable=_flag(data, "scrollable"),
            long_clickable=_flag(data, "long-clickable"),
            is_password=_flag(data, "password"),
            selected=_flag(data, "selected"),
            bounds=Bounds(bounds) if bounds else None,
            drawing_order=data.get("drawing-order", ""),
        )

    @classmethod
    def from_xml_node(cls, node: etree._Element) -> Widget:
        widget = cls.from_dict(node.attrib)
        widget.node = node
        return widget

    # ── Dunder Methods ───────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Widget):
            return NotImplemented
        return (
            self.text == other.text
            and self.id == other.id
            and self.class_name == other.class_name
            and self.package == other.package
            and self.content_desc == other.content_desc
            and self.bounds == other.bounds
        )

    __hash__ = None  # type: ignore[assignment]  # mutable: equal widgets are not hash keys

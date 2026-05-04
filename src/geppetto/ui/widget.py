from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lxml import etree

from .bounds import Bounds

if TYPE_CHECKING:
    from .children import Children


@dataclass
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

    # ── Factory Methods ──────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Widget:
        return cls(
            index=data.get("index", ""),
            text=data.get("text", ""),
            id=data.get("resource-id", ""),
            class_name=data.get("class", ""),
            package=data.get("package", ""),
            content_desc=data.get("content-desc", ""),
            checkable=data.get("checkable", "false").lower() == "true",
            checked=data.get("checked", "false").lower() == "true",
            clickable=data.get("clickable", "false").lower() == "true",
            enabled=data.get("enabled", "false").lower() == "true",
            focusable=data.get("focusable", "false").lower() == "true",
            focused=data.get("focused", "false").lower() == "true",
            scrollable=data.get("scrollable", "false").lower() == "true",
            long_clickable=data.get("long-clickable", "false").lower() == "true",
            is_password=data.get("password", "false").lower() == "true",
            selected=data.get("selected", "false").lower() == "true",
            bounds=Bounds(data["bounds"]),
            drawing_order=data.get("drawing-order", ""),
        )

    @classmethod
    def from_xml_node(cls, node: etree._Element) -> Widget:
        return cls(
            index=node.attrib.get("index", ""),
            text=node.attrib.get("text", ""),
            id=node.attrib.get("resource-id", ""),
            class_name=node.attrib.get("class", ""),
            package=node.attrib.get("package", ""),
            content_desc=node.attrib.get("content-desc", ""),
            checkable=node.attrib.get("checkable", "false").lower() == "true",
            checked=node.attrib.get("checked", "false").lower() == "true",
            clickable=node.attrib.get("clickable", "false").lower() == "true",
            enabled=node.attrib.get("enabled", "false").lower() == "true",
            focusable=node.attrib.get("focusable", "false").lower() == "true",
            focused=node.attrib.get("focused", "false").lower() == "true",
            scrollable=node.attrib.get("scrollable", "false").lower() == "true",
            long_clickable=node.attrib.get("long-clickable", "false").lower() == "true",
            is_password=node.attrib.get("password", "false").lower() == "true",
            selected=node.attrib.get("selected", "false").lower() == "true",
            bounds=Bounds(node.attrib["bounds"]),
            drawing_order=node.attrib.get("drawing-order", ""),
        )

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

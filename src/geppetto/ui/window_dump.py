from __future__ import annotations

from lxml import etree

from ..exceptions import WidgetNotFoundError
from ..models.by import By
from .children import Children
from .widget import Widget


class WindowDump:
    """Parses an Android UI hierarchy XML dump and provides widget search capabilities."""

    def __init__(self, text_dump: str) -> None:
        self._text = text_dump
        self._root: etree._Element | None = None

    # ── Properties ───────────────────────────────────────────────────

    @property
    def root(self) -> etree._Element:
        """Lazily parsed and cached XML root element."""
        if self._root is None:
            try:
                self._root = etree.fromstring(self._text.encode("utf-8"))
            except etree.XMLSyntaxError as e:
                raise ValueError(f"Failed to parse window dump: {e}") from e
        return self._root

    # ── Widget Extraction ────────────────────────────────────────────

    def get_widgets(self) -> list[Widget]:
        return [Widget.from_xml_node(node) for node in self.root.xpath(".//node")]

    def set_children(self, widget: Widget) -> list[Widget]:
        xpath = (
            f".//node[@index='{widget.index}' and @text='{widget.text}' "
            f"and @resource-id='{widget.id}' and @class='{widget.class_name}']"
        )
        parent_nodes = self.root.xpath(xpath)
        children: list[Widget] = []
        if parent_nodes:
            children = [Widget.from_xml_node(child) for child in parent_nodes[0].findall("node")]
        widget.children = Children(children)
        return children

    def find_widget(self, by: By, value: str) -> Widget:
        """Find the first widget matching *by*/*value*.

        Raises:
            WidgetNotFoundError: If no matching widget is found.
        """
        found: Widget | None = None

        if by is By.XPATH:
            nodes = self.root.xpath(value)
            if nodes:
                found = Widget.from_xml_node(nodes[0])
        else:
            for widget in self.get_widgets():
                if getattr(widget, by.value) == value:
                    found = widget
                    break

        if found is None:
            raise WidgetNotFoundError(f"Widget not found using {by.name} with value {value}")

        self.set_children(found)
        return found

    # ── Dunder ───────────────────────────────────────────────────────

    def __str__(self) -> str:
        return self._text

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WindowDump):
            return NotImplemented
        return self._text == other._text

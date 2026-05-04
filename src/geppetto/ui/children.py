from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.by import By

if TYPE_CHECKING:
    from .widget import Widget


class Children(list["Widget"]):
    """A specialised list that supports searching child widgets by :class:`By` strategy."""

    def __init__(self, children: list[Widget] | None = None) -> None:
        super().__init__(children if children is not None else [])

    def get_widget(self, by: By, value: str) -> Widget | None:
        for widget in self:
            if getattr(widget, by.value) == value:
                return widget
        return None

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({super().__str__()})"

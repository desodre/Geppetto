"""``geppetto inspect``: the device screen in the browser, recommended selectors and a recorder
that turns taps and typing into a Python script."""

from .recorder import Recorder
from .selectors import Selector, recommend, xpath_literal
from .server import InspectorServer, hierarchy_json

__all__ = [
    "InspectorServer",
    "Recorder",
    "Selector",
    "hierarchy_json",
    "recommend",
    "xpath_literal",
]

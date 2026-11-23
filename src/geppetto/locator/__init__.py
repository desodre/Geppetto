"""Locators with auto-waiting actions and retrying ``expect()`` assertions."""

from .assertions import LocatorAssertions, expect
from .locator import Locator
from .query import Query

__all__ = ["Locator", "LocatorAssertions", "Query", "expect"]

from enum import Enum


class Direction(Enum):
    UP = "up"
    DOWN = "down"
    # Aliases kept for code written against 2.0 (`Direction.Up`).
    Up = "up"  # noqa: PIE796
    Down = "down"  # noqa: PIE796

from __future__ import annotations


class Bounds:
    """Rectangular region on screen, parsed from Android's ``[x1,y1][x2,y2]`` format.

    Provides geometric helpers (center, dimensions, containment, etc.) used for
    coordinate-based interactions with UI elements.
    """

    __slots__ = ("bounds_str", "x1", "y1", "x2", "y2")

    def __init__(self, bounds_str: str) -> None:
        if not isinstance(bounds_str, str):
            raise TypeError(f"{bounds_str} is not a string")
        if not (bounds_str.startswith("[") and bounds_str.endswith("]")):
            raise ValueError("invalid bounds format - expected '[x1,y1][x2,y2]'")

        try:
            parts = bounds_str[1:-1].split("][")
            if len(parts) != 2:
                raise ValueError
            coords: list[int] = []
            for part in parts:
                x, y = map(int, part.split(","))
                coords.extend([x, y])
        except (ValueError, IndexError) as e:
            raise ValueError(f"invalid bounds format: {bounds_str}") from e

        self.bounds_str = bounds_str
        self.x1, self.y1, self.x2, self.y2 = coords[0], coords[1], coords[2], coords[3]

        if self.x1 > self.x2 or self.y1 > self.y2:
            raise ValueError("invalid bounds - x1 must be <= x2 and y1 must be <= y2")

    # ── Geometric Properties ─────────────────────────────────────────

    @property
    def center(self) -> tuple[float, float]:
        return (self.x2 + self.x1) / 2, (self.y2 + self.y1) / 2

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    # ── Corner / Edge Accessors ──────────────────────────────────────

    @property
    def top_left(self) -> tuple[float, float]:
        return (self.x1, self.y1)

    @property
    def top_right(self) -> tuple[float, float]:
        return (self.x2, self.y1)

    @property
    def bottom_right(self) -> tuple[float, float]:
        return (self.x2, self.y2)

    @property
    def bottom_left(self) -> tuple[float, float]:
        return (self.x1, self.y2)

    @property
    def top_middle(self) -> tuple[float, float]:
        return (self.center[0], self.y1)

    @property
    def bottom_middle(self) -> tuple[float, float]:
        return (self.center[0], self.y2)

    @property
    def left_middle(self) -> tuple[float, float]:
        return (self.x1, self.center[1])

    @property
    def right_middle(self) -> tuple[float, float]:
        return (self.x2, self.center[1])

    # ── Methods ──────────────────────────────────────────────────────

    def contains(self, x: float, y: float) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def midpoint(self, second_point: tuple[float, float]) -> tuple[float, float]:
        x1, y1 = self.center
        x2, y2 = second_point
        return (x1 + x2) / 2, (y1 + y2) / 2

    def to_dict(self) -> dict[str, float | tuple[float, float]]:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "center": self.center,
            "width": self.width,
            "height": self.height,
            "area": self.area,
        }

    # ── Dunder Methods ───────────────────────────────────────────────

    def __str__(self) -> str:
        return self.bounds_str

    def __repr__(self) -> str:
        return f"Bounds([{self.x1},{self.y1}][{self.x2},{self.y2}])"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Bounds):
            return (
                self.x1 == other.x1
                and self.y1 == other.y1
                and self.x2 == other.x2
                and self.y2 == other.y2
            )
        return NotImplemented

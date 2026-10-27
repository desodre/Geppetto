from __future__ import annotations

import math
from enum import Enum
from typing import Any, cast

from PIL import Image
from PIL.Image import Image as PILImage

from .._logging import DeviceLogger
from ..ui.bounds import Bounds

try:
    import extcolors
    import imagehash
    import numpy as np
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "Image analysis dependencies are missing. "
        "Install them with: pip install 'geppetto-android[analyzers]'"
    ) from _exc


class Colors(Enum):
    """Reference RGB colors for :meth:`ScreenAnalyzer.has_colors`.

    Every member has a distinct value: two equal tuples would make the second an alias of
    the first (until 2.0.4 ``ALMOST_BLUE`` *was* ``ALMOST_GREEN``).
    """

    PERFECT_RED = (255, 0, 0)
    PERFECT_GREEN = (0, 255, 0)
    PERFECT_BLUE = (0, 0, 255)
    ALMOST_RED = (220, 40, 40)
    ALMOST_GREEN = (40, 200, 40)
    ALMOST_BLUE = (40, 40, 220)


class ScreenAnalyzer:
    """Image analysis utilities for screenshots and captured frames."""

    def __init__(self, image: str | PILImage, similarity_threshold: int = 5) -> None:
        if isinstance(image, str):
            self.image_path = image
            self.image: PILImage = Image.open(image)
        else:
            self.image_path = "in-memory"
            self.image = image

        self.hash = imagehash.average_hash(self.image)
        self.similarity_threshold = similarity_threshold
        self.logger = DeviceLogger.get_controller_logger("ScreenAnalyzer")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ScreenAnalyzer):
            return NotImplemented
        return bool((self.hash - other.hash) <= self.similarity_threshold)

    def get_diff_brightness(self) -> float:
        grayscale = self.image.convert("L")
        return float(np.mean(np.array(grayscale)))

    def crop_image(
        self, bounds: Bounds, save: bool = False, new_name: str | None = None
    ) -> PILImage:
        """Crop to *bounds* (the analyzer keeps the cropped image).

        Saving is opt-in and needs *new_name*: the original file is never overwritten
        by accident (until 2.0.4 ``save=True`` was the default and replaced it).
        """
        if save and not new_name:
            raise ValueError(
                "crop_image(save=True) needs new_name; the original is not overwritten"
            )
        cropped = self.image.crop((bounds.x1, bounds.y1, bounds.x2, bounds.y2))
        self.logger.info("Cropping image to %s", bounds)
        if save and new_name:
            cropped.save(new_name)
        self.image = cropped
        return cropped

    def color_in_the_image(self) -> tuple[list[Any], int]:
        self.logger.info("Extracting colors from %s", self.image_path)
        return cast(
            tuple[list[Any], int], extcolors.extract_from_image(self.image, tolerance=12, limit=5)
        )

    def get_metadata(self) -> Any:
        return self.image.getexif().items()

    def has_colors(
        self,
        target_colors: list[Colors],
        tolerance: float = 50.0,
    ) -> dict[Colors, bool]:
        """Check whether *target_colors* are present in the image within Euclidean *tolerance*."""
        extracted_colors, _ = self.color_in_the_image()
        result: dict[Colors, bool] = {c: False for c in target_colors}

        for target in target_colors:
            tr, tg, tb = target.value
            for (er, eg, eb), _ in extracted_colors:
                distance = math.sqrt((tr - er) ** 2 + (tg - eg) ** 2 + (tb - eb) ** 2)
                if distance <= tolerance:
                    result[target] = True
                    break

        return result

from __future__ import annotations

import os

from .._logging import DeviceLogger

try:
    import cv2
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "Video analysis dependencies are missing. "
        "Install them with: pip install geppetto[analyzers]"
    ) from _exc


from PIL import Image
from PIL.Image import Image as PILImage


class VideoAnalyzer:
    """Extract and analyse frames from screen-recorded videos."""

    def __init__(self, video_path: str) -> None:
        self.video_path = video_path
        self.logger = DeviceLogger.get_controller_logger("VideoAnalyzer")

    def extract_frames(self, output_dir: str, frame_interval: int = 1) -> list[str]:
        """Save every *frame_interval*-th frame as a JPEG to *output_dir*."""
        os.makedirs(output_dir, exist_ok=True)

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {self.video_path}")

        saved_paths: list[str] = []
        frame_count = 0
        saved_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % frame_interval == 0:
                path = os.path.join(output_dir, f"frame_{saved_count:04d}.jpg")
                cv2.imwrite(path, frame)
                self.logger.info("Saving %s", path)
                saved_paths.append(os.path.abspath(path))
                saved_count += 1
            frame_count += 1

        cap.release()
        return saved_paths

    def yield_frames(self, frame_interval: int = 1):
        """Yield every *frame_interval*-th frame as a PIL Image."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {self.video_path}")

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % frame_interval == 0:
                # Convert BGR (OpenCV) to RGB (PIL)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                yield Image.fromarray(frame_rgb)
            frame_count += 1

        cap.release()

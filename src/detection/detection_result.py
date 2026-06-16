"""Domain entity representing a single YOLO detection result."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

import numpy as np


@dataclass
class DetectionResult:
    """A single object detected by the YOLO model.

    Attributes:
        bounding_box: Bounding box in ``(x1, y1, x2, y2)`` format
            where ``(x1, y1)`` is the top-left corner and
            ``(x2, y2)`` is the bottom-right corner, both in
            pixel coordinates relative to the original frame.
        confidence: Detection confidence score in the range
            ``[0.0, 1.0]``.
        class_id: Integer class ID predicted by the model.
        class_name: Human-readable class label (e.g. ``"plate"``).
    """

    bounding_box: Tuple[int, int, int, int] = field(
        default_factory=lambda: (0, 0, 0, 0),
    )
    confidence: float = 0.0
    class_id: int = 0
    class_name: str = ""

    @property
    def x1(self) -> int:
        """Left edge of the bounding box."""
        return self.bounding_box[0]

    @property
    def y1(self) -> int:
        """Top edge of the bounding box."""
        return self.bounding_box[1]

    @property
    def x2(self) -> int:
        """Right edge of the bounding box."""
        return self.bounding_box[2]

    @property
    def y2(self) -> int:
        """Bottom edge of the bounding box."""
        return self.bounding_box[3]

    @property
    def width(self) -> int:
        """Width of the bounding box in pixels."""
        return self.bounding_box[2] - self.bounding_box[0]

    @property
    def height(self) -> int:
        """Height of the bounding box in pixels."""
        return self.bounding_box[3] - self.bounding_box[1]

    @property
    def area(self) -> int:
        """Area of the bounding box in square pixels."""
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        """Center point ``(cx, cy)`` of the bounding box."""
        return (
            (self.bounding_box[0] + self.bounding_box[2]) / 2.0,
            (self.bounding_box[1] + self.bounding_box[3]) / 2.0,
        )

    def crop_frame(self, frame: np.ndarray) -> np.ndarray:
        """Extract the region of interest from a frame.

        Args:
            frame: The source frame as a BGR numpy array.

        Returns:
            The cropped sub-image corresponding to the bounding box.
            If the bounding box is out of bounds, an empty array is
            returned.

        """
        h, w = frame.shape[:2]
        x1 = max(0, self.bounding_box[0])
        y1 = max(0, self.bounding_box[1])
        x2 = min(w, self.bounding_box[2])
        y2 = min(h, self.bounding_box[3])
        if x2 <= x1 or y2 <= y1:
            return np.array([], dtype=np.uint8)
        return frame[y1:y2, x1:x2].copy()

    def __repr__(self) -> str:
        return (
            f"<DetectionResult class={self.class_name!r} "
            f"conf={self.confidence:.3f} "
            f"bbox=({self.x1},{self.y1},{self.x2},{self.y2})>"
        )

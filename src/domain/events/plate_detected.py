"""Domain event emitted when a license plate is detected."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PlateDetected:
    """Emitted when YOLOv8 detects a potential plate above the confidence threshold."""

    camera_id: int
    """The camera that captured the frame."""

    bounding_box: tuple[int, int, int, int]
    """The bounding box coordinates (x1, y1, x2, y2)."""

    confidence: float
    """YOLOv8 detection confidence (0.0–1.0)."""

    timestamp: datetime
    """When the frame was captured."""

"""Data Transfer Objects for Camera operations.

DTOs decouple the API/presentation layer from the domain model.
They carry only the data needed for a specific operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CreateCameraRequest:
    """Request DTO for creating a new camera."""

    name: str
    """Unique camera name."""

    camera_type: str
    """``"rtsp"`` or ``"usb"``."""

    rtsp_url: str | None = None
    """RTSP stream URL (required for RTSP)."""

    usb_index: int | None = None
    """USB device index (required for USB)."""

    confidence_threshold: float = 0.5
    """Detection confidence threshold (0.0–1.0)."""

    evidence_mode: str = "snapshot"
    """Evidence capture mode: ``"none"``, ``"snapshot"``, ``"video"``, or
    ``"both"``."""


@dataclass
class UpdateCameraRequest:
    """Request DTO for updating an existing camera.

    Only non-``None`` fields will be updated.
    """

    name: str | None = None
    """New camera name."""

    rtsp_url: str | None = None
    """New RTSP URL. Set to empty string to clear."""

    usb_index: int | None = None
    """New USB index. Set to -1 to clear."""

    confidence_threshold: float | None = None
    """New confidence threshold."""

    evidence_mode: str | None = None
    """New evidence mode. ``None`` means unchanged."""


@dataclass
class CameraDTO:
    """Response DTO representing a camera."""

    id: int
    name: str
    camera_type: str
    rtsp_url: str | None
    usb_index: int | None
    enabled: bool
    confidence_threshold: float
    evidence_mode: str
    created_at: datetime | None
    updated_at: datetime | None

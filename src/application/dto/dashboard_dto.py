"""Data Transfer Objects for the Dashboard view.

These DTOs aggregate data from multiple repositories into a single
snapshot that the dashboard UI can render without coupling to the
database or domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CameraStatusDTO:
    """Runtime status of a single camera for dashboard display.

    Attributes:
        id: Camera primary key.
        name: User-friendly camera name.
        camera_type: ``"rtsp"`` or ``"usb"``.
        enabled: Whether the camera is enabled for detection.
        status: Current health status string: ``"online"``,
            ``"offline"``, ``"reconnecting"``, ``"error"``,
            or ``"disabled"``.
        detection_count_today: Number of detections for this camera
            since midnight.
        fps: Current frames-per-second (0.0 if unknown / offline).
        last_seen: Timestamp of the last received frame, or ``None``.

    """

    id: int
    name: str
    camera_type: str
    enabled: bool
    status: str = "disabled"
    detection_count_today: int = 0
    fps: float = 0.0
    last_seen: Optional[datetime] = None


@dataclass
class DetectionSummaryDTO:
    """A single detection record for the recent-detections table.

    Attributes:
        id: Detection primary key.
        camera_id: Source camera ID.
        camera_name: Source camera name (resolved for display).
        plate_text: Recognised licence plate text (may be empty).
        confidence: OCR / detection confidence (0.0–1.0).
        snapshot_path: Filesystem path to the snapshot image.
        video_path: Filesystem path to the video clip.
        webhook_status: Delivery status of the webhook.
        detected_at: When the detection occurred.

    """

    id: int
    camera_id: int
    camera_name: str
    plate_text: str
    confidence: float
    snapshot_path: str
    video_path: str
    webhook_status: str
    detected_at: datetime


@dataclass
class DashboardData:
    """Complete snapshot of dashboard state at a point in time.

    This is the primary data structure returned by
    ``DashboardService.refresh()``.

    Attributes:
        cameras: Per-camera status and stats.
        total_detections_today: Aggregate count across all cameras.
        detection_count_by_camera: Map of ``camera_id → count``.
        recent_detections: Most recent N detection records.
        cameras_online: Number of cameras currently online.
        cameras_offline: Number of cameras offline or in an error state.
        cameras_disabled: Number of cameras that are intentionally disabled.
        refreshed_at: Timestamp when this snapshot was built.

    """

    cameras: list[CameraStatusDTO] = field(default_factory=list)
    total_detections_today: int = 0
    detection_count_by_camera: dict[int, int] = field(default_factory=dict)
    recent_detections: list[DetectionSummaryDTO] = field(default_factory=list)
    cameras_online: int = 0
    cameras_offline: int = 0
    cameras_disabled: int = 0
    refreshed_at: Optional[datetime] = None

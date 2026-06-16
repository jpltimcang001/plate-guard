"""Domain entities for webhook payloads and delivery results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class WebhookPayload:
    """The data transmitted in a single webhook request.

    Attributes:
        event_type: A label identifying the kind of event (e.g.
            ``"plate_detected"``, ``"camera_offline"``).
        camera_id: The source camera ID.
        plate_text: Recognised license plate text (may be empty if
            OCR was skipped or failed).
        detection_confidence: YOLO detection confidence.
        ocr_confidence: PaddleOCR confidence (``0.0`` if unavailable).
        timestamp: When the detection occurred.
        snapshot_image: Optional BGR snapshot of the detected frame.
            Included only when the webhook config has
            ``send_image=True``.
        video_bytes: Optional video clip bytes.  Included only when
            the webhook config has ``send_video=True``.
        metadata: Additional key-value pairs to include in the JSON
            body (e.g. bounding box coordinates, camera name).
    """

    event_type: str = "plate_detected"
    camera_id: int = 0
    plate_text: str = ""
    detection_confidence: float = 0.0
    ocr_confidence: float = 0.0
    timestamp: Optional[datetime] = None
    snapshot_image: Optional[np.ndarray] = None
    video_bytes: Optional[bytes] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def has_image(self) -> bool:
        """Whether a snapshot image is attached."""
        return self.snapshot_image is not None and self.snapshot_image.size > 0

    @property
    def has_video(self) -> bool:
        """Whether a video clip is attached."""
        return self.video_bytes is not None and len(self.video_bytes) > 0

    def to_json_dict(self) -> Dict[str, object]:
        """Serialise the payload to a JSON-safe dictionary.

        Image and video data are **not** included in the dict; they
        are sent as multipart attachments instead.

        Returns:
            A dict suitable for ``json.dumps``.
        """
        result: Dict[str, object] = {
            "event": self.event_type,
            "camera_id": self.camera_id,
            "plate": self.plate_text,
            "detection_confidence": round(self.detection_confidence, 4),
            "ocr_confidence": round(self.ocr_confidence, 4),
        }

        if self.timestamp is not None:
            result["timestamp"] = self.timestamp.isoformat()

        result["has_image"] = self.has_image
        result["has_video"] = self.has_video
        result.update(self.metadata)
        return result


@dataclass
class WebhookResult:
    """The outcome of a single webhook delivery attempt.

    Attributes:
        webhook_id: The database ID of the webhook configuration that
            was invoked.
        url: The target URL (useful for logging).
        status_code: HTTP status code from the server (``0`` if the
            request could not be made).
        success: Whether the delivery is considered successful
            (HTTP 2xx).
        attempt: Which attempt number this result represents
            (1-indexed).
        total_attempts: How many attempts were made (including this
            one).
        error_message: Human-readable error description if the
            request failed.
        response_body: Truncated response body for debugging.
        elapsed_ms: Round-trip time in milliseconds.
    """

    webhook_id: int = 0
    url: str = ""
    status_code: int = 0
    success: bool = False
    attempt: int = 1
    total_attempts: int = 1
    error_message: str = ""
    response_body: str = ""
    elapsed_ms: float = 0.0

    def __repr__(self) -> str:
        status = "ok" if self.success else "fail"
        return (
            f"<WebhookResult id={self.webhook_id} "
            f"status={self.status_code} "
            f"{status} "
            f"attempt={self.attempt}/{self.total_attempts}>"
        )

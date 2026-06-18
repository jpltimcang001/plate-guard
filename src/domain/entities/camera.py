"""Camera domain entity.

This is a pure domain entity with no ORM or framework dependencies.
It serves as the aggregate root for the Camera aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.domain.value_objects.camera_type import CameraType


@dataclass
class Camera:
    """Represents a camera source (RTSP or USB).

    This is a plain Python dataclass used as the domain entity.
    It is decoupled from the SQLAlchemy ORM model (CameraModel).
    """

    id: int | None = field(default=None, compare=False)
    """Primary key. ``None`` until persisted."""

    name: str = ""
    """User-friendly camera name (must be unique in the system)."""

    type: CameraType = CameraType.RTSP
    """The camera source type: RTSP or USB."""

    rtsp_url: Optional[str] = None
    """RTSP stream URL. Required if ``type == CameraType.RTSP``."""

    usb_index: Optional[int] = None
    """USB device index. Required if ``type == CameraType.USB``."""

    enabled: bool = False
    """Whether the camera is enabled for detection."""

    confidence_threshold: float = 0.5
    """Minimum YOLOv8 confidence (0.0–1.0) for detection."""

    evidence_mode: str = "snapshot"
    """Evidence capture mode: ``"none"``, ``"snapshot"``, ``"video"``, or
    ``"both"``.  Controls whether snapshots and/or video clips are
    captured on detection."""

    created_at: Optional[datetime] = None
    """Timestamp when the camera was created."""

    updated_at: Optional[datetime] = None
    """Timestamp when the camera was last updated."""

    # ------------------------------------------------------------------
    # Domain behaviour
    # ------------------------------------------------------------------

    def enable(self) -> None:
        """Enable the camera for detection."""
        self.enabled = True

    def disable(self) -> None:
        """Disable the camera (stop detection)."""
        self.enabled = False

    def is_rtsp(self) -> bool:
        """Return ``True`` if this is an RTSP camera."""
        return self.type == CameraType.RTSP

    def is_usb(self) -> bool:
        """Return ``True`` if this is a USB camera."""
        return self.type == CameraType.USB

    def validate(self) -> None:
        """Validate the camera's business rules.

        Raises:
            ValueError: If any constraint is violated.

        """
        if not self.name or not self.name.strip():
            raise ValueError("Camera name must not be empty.")

        if self.is_rtsp() and not self.rtsp_url:
            raise ValueError("RTSP URL is required for RTSP cameras.")

        if self.is_usb() and self.usb_index is None:
            raise ValueError("USB index is required for USB cameras.")

        if self.is_usb() and self.usb_index is not None and self.usb_index < 0:
            raise ValueError("USB index must be a non-negative integer.")

        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                f"Confidence threshold must be between 0.0 and 1.0, "
                f"got {self.confidence_threshold}",
            )

        valid_modes = {"none", "snapshot", "video", "both"}
        if self.evidence_mode not in valid_modes:
            raise ValueError(
                f"Evidence mode must be one of {valid_modes}, "
                f"got {self.evidence_mode!r}",
            )

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def create_rtsp(
        cls,
        name: str,
        rtsp_url: str,
        confidence_threshold: float = 0.5,
    ) -> Camera:
        """Create a new RTSP camera.

        Args:
            name: Unique camera name.
            rtsp_url: RTSP stream URL.
            confidence_threshold: Detection confidence threshold.

        Returns:
            A new Camera instance.

        """
        camera = cls(
            name=name,
            type=CameraType.RTSP,
            rtsp_url=rtsp_url,
            usb_index=None,
            confidence_threshold=confidence_threshold,
        )
        camera.validate()
        return camera

    @classmethod
    def create_usb(
        cls,
        name: str,
        usb_index: int,
        confidence_threshold: float = 0.5,
    ) -> Camera:
        """Create a new USB camera.

        Args:
            name: Unique camera name.
            usb_index: USB device index.
            confidence_threshold: Detection confidence threshold.

        Returns:
            A new Camera instance.

        """
        camera = cls(
            name=name,
            type=CameraType.USB,
            rtsp_url=None,
            usb_index=usb_index,
            confidence_threshold=confidence_threshold,
        )
        camera.validate()
        return camera

    # ------------------------------------------------------------------
    # Model conversion
    # ------------------------------------------------------------------

    @classmethod
    def from_model(cls, model: Any) -> Camera:
        """Convert an ORM CameraModel to a domain Camera entity.

        Also accepts an already-converted ``Camera`` instance (returning
        it unchanged) so that callers can safely convert both ORM models
        and domain entities.

        Args:
            model: A ``CameraModel`` or ``Camera`` instance.

        Returns:
            A ``Camera`` domain entity.

        """
        if isinstance(model, cls):
            return model

        # Import here to avoid circular import at module level
        from src.database.models.camera_model import CameraModel

        if not isinstance(model, CameraModel):
            msg = f"Expected CameraModel or Camera, got {type(model).__name__}"
            raise TypeError(msg)

        type_map = {"rtsp": CameraType.RTSP, "usb": CameraType.USB}
        cam_type = type_map.get(model.type, CameraType.RTSP)

        return cls(
            id=model.id,
            name=model.name,
            type=cam_type,
            rtsp_url=model.rtsp_url,
            usb_index=model.usb_index,
            enabled=model.enabled,
            confidence_threshold=model.confidence_threshold,
            evidence_mode=model.evidence_mode,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @classmethod
    def from_model_list(cls, models: list[Any]) -> list[Camera]:
        """Convert a list of ORM CameraModels to domain Camera entities.

        Args:
            models: A list of ``CameraModel`` or ``Camera`` instances.

        Returns:
            A list of ``Camera`` domain entities.

        """
        return [cls.from_model(m) for m in models]

    def __repr__(self) -> str:
        return (
            f"<Camera id={self.id} name={self.name!r} "
            f"type={self.type.value} enabled={self.enabled}>"
        )

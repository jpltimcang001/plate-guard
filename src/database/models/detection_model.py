"""SQLAlchemy ORM model for the ``detections`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.engine import Base


class DetectionModel(Base):
    """Represents a single license plate detection event.

    Columns mirror the ``detections`` table in the ERD with
    added timestamps and a back-reference to the source camera.
    """

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plate_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Recognized license plate text (None if OCR failed)",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="OCR confidence score (0.0–1.0)",
    )
    image_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="Filesystem path to the snapshot image",
    )
    video_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="Filesystem path to the video clip",
    )
    webhook_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_configured",
        comment="Webhook delivery status: not_configured, pending, success, failed",
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    camera: Mapped["CameraModel"] = relationship(
        "CameraModel",
        back_populates="detections",
    )

    def __repr__(self) -> str:
        return (
            f"<DetectionModel id={self.id} camera_id={self.camera_id} "
            f"plate={self.plate_number!r} conf={self.confidence:.3f}>"
        )

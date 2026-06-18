"""SQLAlchemy ORM model for the ``cameras`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.engine import Base


class CameraModel(Base):
    """Represents a camera source (RTSP or USB).

    Columns mirror the ``cameras`` table in the ERD with
    added timestamps and relationships.
    """

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # "rtsp" | "usb"
    rtsp_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    usb_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    confidence_threshold: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        nullable=False,
    )
    evidence_mode: Mapped[str] = mapped_column(
        String(16),
        default="snapshot",
        nullable=False,
        comment="Evidence mode: none, snapshot, video, or both",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    zones: Mapped[list["ZoneModel"]] = relationship(
        "ZoneModel",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    webhooks: Mapped[list["WebhookModel"]] = relationship(
        "WebhookModel",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    detections: Mapped[list["DetectionModel"]] = relationship(
        "DetectionModel",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CameraModel id={self.id} name={self.name!r} "
            f"type={self.type} enabled={self.enabled}>"
        )

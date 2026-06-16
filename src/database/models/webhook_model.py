"""SQLAlchemy ORM model for the ``webhooks`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.engine import Base


class WebhookModel(Base):
    """Represents a webhook configuration attached to a camera.

    Columns mirror the ``webhooks`` table in the ERD with
    added timestamps and a back-reference to the parent camera.
    """

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="HTTP method: GET, POST, PUT, or PATCH",
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    headers_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="JSON object of custom HTTP headers",
    )
    auth_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="none",
        comment="Authentication type: none, basic, bearer, api_key",
    )
    auth_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Authentication credential (token, key, or user:pass)",
    )
    body_template: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="JSON template for the webhook request body",
    )
    send_image: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether to attach the snapshot image",
    )
    send_video: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether to attach the video clip",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    camera: Mapped["CameraModel"] = relationship(
        "CameraModel",
        back_populates="webhooks",
    )

    def __repr__(self) -> str:
        return (
            f"<WebhookModel id={self.id} camera_id={self.camera_id} "
            f"method={self.method} url={self.url[:50]!r}...>"
        )

"""SQLAlchemy ORM model for the ``zones`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.engine import Base


class ZoneModel(Base):
    """Represents a single polygon detection zone for a camera.

    Columns mirror the ``zones`` table in the ERD with
    added timestamps and a back-reference to the parent camera.
    """

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    polygon_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON array of [x, y] vertex coordinates, e.g. [[10,20],[30,40],[50,60]]",
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
        back_populates="zones",
    )

    def __repr__(self) -> str:
        return (
            f"<ZoneModel id={self.id} name={self.name!r} "
            f"camera_id={self.camera_id}>"
        )

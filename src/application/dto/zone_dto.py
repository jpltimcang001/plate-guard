"""Data Transfer Objects for Zone operations.

DTOs decouple the API/presentation layer from the domain model.
They carry only the data needed for a specific operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CreateZoneRequest:
    """Request DTO for creating a new detection zone."""

    name: str
    """Zone name (must be unique per camera)."""

    camera_id: int
    """ID of the parent camera."""

    points: list[tuple[float, float]] = field(default_factory=list)
    """Polygon vertices as ``(x, y)`` pixel coordinates (min 3)."""


@dataclass
class UpdateZoneRequest:
    """Request DTO for updating an existing zone.

    Only non-``None`` fields will be updated.
    """

    name: str | None = None
    """New zone name."""

    points: list[tuple[float, float]] | None = None
    """New polygon vertices."""


@dataclass
class ZoneDTO:
    """Response DTO representing a detection zone."""

    id: int
    name: str
    camera_id: int
    points: list[tuple[float, float]]
    created_at: datetime | None

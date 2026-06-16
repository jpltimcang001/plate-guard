"""Zone domain entity representing a single detection polygon.

A Zone defines a region of interest within a camera's field of view.
Detection events are only generated for license plates that fall within
at least one enabled zone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Zone:
    """Represents a polygon detection zone.

    This is a plain Python dataclass decoupled from the SQLAlchemy ORM
    model (``ZoneModel``). Points are stored as a list of ``(x, y)``
    tuples representing vertex coordinates in the camera's pixel space.
    """

    id: int | None = field(default=None, compare=False)
    """Primary key. ``None`` until persisted."""

    camera_id: int = 0
    """Foreign key referencing the parent camera."""

    name: str = ""
    """User-friendly zone name (unique per camera)."""

    points: list[tuple[float, float]] = field(default_factory=list)
    """Polygon vertices as ``(x, y)`` pixel coordinates."""

    created_at: datetime | None = None
    """Timestamp when the zone was created."""

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def point_count(self) -> int:
        """Return the number of vertices in the polygon."""
        return len(self.points)

    @property
    def is_closed(self) -> bool:
        """Return ``True`` if the polygon has at least 3 points."""
        return len(self.points) >= 3

    @property
    def polygon_json(self) -> str:
        """Serialize points to a JSON string for persistence."""
        return json.dumps([[float(x), float(y)] for x, y in self.points])

    @staticmethod
    def points_from_json(json_str: str) -> list[tuple[float, float]]:
        """Deserialize a JSON string back to a point list.

        Args:
            json_str: JSON array of ``[x, y]`` pairs.

        Returns:
            A list of ``(x, y)`` tuples.

        """
        raw: list[list[float]] = json.loads(json_str)
        return [(float(x), float(y)) for x, y in raw]

    @staticmethod
    def points_to_json(points: list[tuple[float, float]]) -> str:
        """Serialize a point list to a JSON string.

        Args:
            points: List of ``(x, y)`` tuples.

        Returns:
            A JSON string representation.

        """
        return json.dumps([[float(x), float(y)] for x, y in points])

    # ------------------------------------------------------------------
    # Domain behaviour
    # ------------------------------------------------------------------

    def add_point(self, x: float, y: float) -> None:
        """Append a vertex to the polygon.

        Args:
            x: X-coordinate in pixel space.
            y: Y-coordinate in pixel space.

        """
        self.points.append((x, y))

    def insert_point(self, index: int, x: float, y: float) -> None:
        """Insert a vertex at a specific index.

        Args:
            index: Position at which to insert (0-based).
            x: X-coordinate.
            y: Y-coordinate.

        Raises:
            IndexError: If *index* is out of range.

        """
        self.points.insert(index, (x, y))

    def remove_point(self, index: int) -> tuple[float, float]:
        """Remove a vertex and return it.

        Args:
            index: The index of the vertex to remove.

        Returns:
            The removed ``(x, y)`` tuple.

        Raises:
            ValueError: If removing would leave fewer than 3 points.
            IndexError: If *index* is out of range.

        """
        if len(self.points) <= 3:
            raise ValueError("Cannot remove point: polygon requires at least 3 vertices.")
        return self.points.pop(index)

    def move_point(self, index: int, x: float, y: float) -> None:
        """Reposition an existing vertex.

        Args:
            index: The vertex index to move.
            x: New X-coordinate.
            y: New Y-coordinate.

        Raises:
            IndexError: If *index* is out of range.

        """
        self.points[index] = (x, y)

    def clear_points(self) -> None:
        """Remove all vertices."""
        self.points.clear()

    def validate(self) -> None:
        """Validate business rules.

        Raises:
            ValueError: If any constraint is violated.

        """
        if not self.name or not self.name.strip():
            raise ValueError("Zone name must not be empty.")

        if self.camera_id <= 0:
            raise ValueError("Zone must be associated with a valid camera.")

        if len(self.points) < 3:
            raise ValueError(
                f"Zone requires at least 3 vertices, got {len(self.points)}."
            )

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        name: str,
        camera_id: int,
        points: list[tuple[float, float]],
    ) -> Zone:
        """Create a new validated zone.

        Args:
            name: Zone name (unique per camera).
            camera_id: ID of the parent camera.
            points: Polygon vertices ``(x, y)``.

        Returns:
            A new ``Zone`` instance.

        """
        zone = cls(
            name=name,
            camera_id=camera_id,
            points=list(points),
        )
        zone.validate()
        return zone

    def __repr__(self) -> str:
        return (
            f"<Zone id={self.id} name={self.name!r} "
            f"camera_id={self.camera_id} points={len(self.points)}>"
        )

"""Unit tests for the Zone domain entity.

These tests validate the pure domain logic with no dependencies
on databases, repositories, or UI frameworks.
"""

from __future__ import annotations

import json

import pytest

from src.domain.entities.zone import Zone
from src.application.exceptions.zone_errors import ZoneNotFoundError, DuplicateZoneNameError


class TestZoneCreate:
    """Tests for Zone factory methods and constructor."""

    def test_create_valid_zone(self) -> None:
        """Creating a zone with valid data sets correct attributes."""
        zone = Zone.create(
            name="Entrance",
            camera_id=1,
            points=[(10, 20), (100, 20), (100, 100), (10, 100)],
        )
        assert zone.name == "Entrance"
        assert zone.camera_id == 1
        assert len(zone.points) == 4
        assert zone.points == [(10.0, 20.0), (100.0, 20.0), (100.0, 100.0), (10.0, 100.0)]
        assert zone.id is None
        assert zone.is_closed is True
        assert zone.point_count == 4

    def test_create_zone_minimum_points(self) -> None:
        """A zone can be created with exactly 3 points."""
        zone = Zone.create(
            name="Triangle",
            camera_id=1,
            points=[(0, 0), (50, 100), (100, 0)],
        )
        assert zone.is_closed
        assert zone.point_count == 3

    def test_create_zone_empty_name_raises(self) -> None:
        """Creating a zone with an empty name raises ValueError."""
        with pytest.raises(ValueError, match="Zone name must not be empty"):
            Zone.create(name="", camera_id=1, points=[(0, 0), (50, 50), (100, 0)])

    def test_create_zone_blank_name_raises(self) -> None:
        """Creating a zone with a blank name raises ValueError."""
        with pytest.raises(ValueError, match="Zone name must not be empty"):
            Zone.create(name="   ", camera_id=1, points=[(0, 0), (50, 50), (100, 0)])

    def test_create_zone_invalid_camera_id_raises(self) -> None:
        """Creating a zone with camera_id=0 raises ValueError."""
        with pytest.raises(ValueError, match="valid camera"):
            Zone.create(name="Zone", camera_id=0, points=[(0, 0), (50, 50), (100, 0)])

    def test_create_zone_negative_camera_id_raises(self) -> None:
        """Creating a zone with a negative camera_id raises ValueError."""
        with pytest.raises(ValueError, match="valid camera"):
            Zone.create(name="Zone", camera_id=-1, points=[(0, 0), (50, 50), (100, 0)])

    def test_create_zone_less_than_three_points_raises(self) -> None:
        """Creating a zone with fewer than 3 points raises ValueError."""
        with pytest.raises(ValueError, match="at least 3 vertices"):
            Zone.create(
                name="Bad Zone",
                camera_id=1,
                points=[(0, 0), (50, 50)],
            )

    def test_create_zone_empty_points_raises(self) -> None:
        """Creating a zone with no points raises ValueError."""
        with pytest.raises(ValueError, match="at least 3 vertices"):
            Zone.create(name="Empty", camera_id=1, points=[])


class TestZonePointManipulation:
    """Tests for point add/remove/move/insert operations."""

    def test_add_point(self) -> None:
        """Adding a point appends to the vertex list."""
        zone = Zone.create(name="Z", camera_id=1, points=[(0, 0), (50, 50), (100, 0)])
        zone.add_point(150, 50)
        assert zone.point_count == 4
        assert zone.points[-1] == (150.0, 50.0)

    def test_insert_point(self) -> None:
        """Inserting a point places it at the correct index."""
        zone = Zone.create(name="Z", camera_id=1, points=[(0, 0), (50, 50), (100, 0)])
        zone.insert_point(1, 25, 25)
        assert zone.points == [(0.0, 0.0), (25.0, 25.0), (50.0, 50.0), (100.0, 0.0)]

    def test_remove_point(self) -> None:
        """Removing a point reduces the vertex count."""
        zone = Zone.create(
            name="Z", camera_id=1, points=[(0, 0), (50, 50), (100, 0), (50, -50)]
        )
        removed = zone.remove_point(1)
        assert removed == (50.0, 50.0)
        assert zone.point_count == 3
        assert zone.points == [(0.0, 0.0), (100.0, 0.0), (50.0, -50.0)]

    def test_remove_point_below_minimum_raises(self) -> None:
        """Removing a point when only 3 remain raises ValueError."""
        zone = Zone.create(name="Z", camera_id=1, points=[(0, 0), (50, 50), (100, 0)])
        with pytest.raises(ValueError, match="at least 3 vertices"):
            zone.remove_point(0)

    def test_move_point(self) -> None:
        """Moving a point updates its coordinates."""
        zone = Zone.create(name="Z", camera_id=1, points=[(0, 0), (50, 50), (100, 0)])
        zone.move_point(1, 60, 60)
        assert zone.points[1] == (60.0, 60.0)

    def test_clear_points(self) -> None:
        """Clearing points removes all vertices."""
        zone = Zone.create(name="Z", camera_id=1, points=[(0, 0), (50, 50), (100, 0)])
        zone.clear_points()
        assert zone.point_count == 0
        assert zone.is_closed is False


class TestZoneSerialization:
    """Tests for JSON serialization of zone points."""

    def test_polygon_json_property(self) -> None:
        """polygon_json serialises points correctly."""
        zone = Zone.create(
            name="Z", camera_id=1, points=[(10.5, 20.3), (100, 200), (50, 0)]
        )
        expected = json.dumps([[10.5, 20.3], [100.0, 200.0], [50.0, 0.0]])
        assert json.loads(zone.polygon_json) == json.loads(expected)

    def test_points_from_json(self) -> None:
        """points_from_json deserializes correctly."""
        json_str = '[[10, 20], [100, 200], [50, 0]]'
        points = Zone.points_from_json(json_str)
        assert points == [(10.0, 20.0), (100.0, 200.0), (50.0, 0.0)]

    def test_points_to_json(self) -> None:
        """points_to_json serializes correctly."""
        points = [(10.5, 20.3), (100.0, 200.0), (50.0, 0.0)]
        result = Zone.points_to_json(points)
        expected = json.dumps([[10.5, 20.3], [100.0, 200.0], [50.0, 0.0]])
        assert json.loads(result) == json.loads(expected)

    def test_roundtrip_json(self) -> None:
        """Points survive a JSON round-trip."""
        original = [(0.1, 0.2), (100.5, 200.7), (300.0, 400.0)]
        json_str = Zone.points_to_json(original)
        restored = Zone.points_from_json(json_str)
        assert restored == original


class TestZoneValidation:
    """Tests for the zone validate() method."""

    def test_valid_zone_passes_validation(self) -> None:
        """A correctly constructed zone passes validation."""
        zone = Zone.create(
            name="Valid Zone",
            camera_id=1,
            points=[(0, 0), (100, 0), (50, 100)],
        )
        # Should not raise
        zone.validate()

    def test_validate_empty_name_raises(self) -> None:
        """Validation catches empty name."""
        zone = Zone(name="", camera_id=1, points=[(0, 0), (100, 0), (50, 100)])
        with pytest.raises(ValueError, match="Zone name must not be empty"):
            zone.validate()

    def test_validate_invalid_camera_id_raises(self) -> None:
        """Validation catches camera_id=0."""
        zone = Zone(name="Z", camera_id=0, points=[(0, 0), (100, 0), (50, 100)])
        with pytest.raises(ValueError, match="valid camera"):
            zone.validate()

    def test_validate_insufficient_points_raises(self) -> None:
        """Validation catches fewer than 3 points."""
        zone = Zone(name="Z", camera_id=1, points=[(0, 0), (100, 0)])
        with pytest.raises(ValueError, match="at least 3 vertices"):
            zone.validate()


class TestZoneProperties:
    """Tests for Zone derived properties."""

    def test_is_closed_true_with_three_points(self) -> None:
        """is_closed is True with 3+ points."""
        zone = Zone(name="Z", camera_id=1, points=[(0, 0), (50, 50), (100, 0)])
        assert zone.is_closed is True

    def test_is_closed_false_with_less_than_three(self) -> None:
        """is_closed is False with fewer than 3 points."""
        zone = Zone(name="Z", camera_id=1, points=[(0, 0), (50, 50)])
        assert zone.is_closed is False

    def test_point_count(self) -> None:
        """point_count returns the correct count."""
        zone = Zone(name="Z", camera_id=1, points=[(0, 0), (50, 50), (100, 0), (50, -50)])
        assert zone.point_count == 4

    def test_repr(self) -> None:
        """Zone has a meaningful repr."""
        zone = Zone.create(name="Main Gate", camera_id=2, points=[(0, 0), (100, 0), (50, 100)])
        r = repr(zone)
        assert "Zone" in r
        assert "Main Gate" in r
        assert "camera_id=2" in r
        assert "points=3" in r

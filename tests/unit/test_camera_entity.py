"""Unit tests for the Camera domain entity.

These tests validate the pure domain logic, with no dependencies
on databases, repositories, or frameworks.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.entities.camera import Camera
from src.domain.value_objects.camera_type import CameraType


class TestCameraCreate:
    """Tests for Camera factory methods and constructor."""

    def test_create_rtsp_camera(self) -> None:
        """Creating an RTSP camera via the factory sets correct attributes."""
        camera = Camera.create_rtsp(
            name="Front Gate",
            rtsp_url="rtsp://192.168.1.100:554/stream",
            confidence_threshold=0.7,
        )
        assert camera.name == "Front Gate"
        assert camera.type == CameraType.RTSP
        assert camera.rtsp_url == "rtsp://192.168.1.100:554/stream"
        assert camera.usb_index is None
        assert camera.enabled is False
        assert camera.confidence_threshold == 0.7
        assert camera.id is None  # Not yet persisted

    def test_create_usb_camera(self) -> None:
        """Creating a USB camera via the factory sets correct attributes."""
        camera = Camera.create_usb(
            name="Lobby USB",
            usb_index=2,
            confidence_threshold=0.5,
        )
        assert camera.name == "Lobby USB"
        assert camera.type == CameraType.USB
        assert camera.usb_index == 2
        assert camera.rtsp_url is None
        assert camera.enabled is False

    def test_create_rtsp_camera_empty_name_raises(self) -> None:
        """Creating an RTSP camera with an empty name raises ValueError."""
        with pytest.raises(ValueError, match="Camera name must not be empty"):
            Camera.create_rtsp(name="", rtsp_url="rtsp://10.0.0.1/stream")

    def test_create_rtsp_camera_blank_name_raises(self) -> None:
        """Creating an RTSP camera with whitespace-only name raises."""
        with pytest.raises(ValueError, match="Camera name must not be empty"):
            Camera.create_rtsp(name="   ", rtsp_url="rtsp://10.0.0.1/stream")

    def test_create_rtsp_camera_empty_url_raises(self) -> None:
        """Creating an RTSP camera without a URL raises ValueError."""
        with pytest.raises(ValueError, match="RTSP URL is required"):
            Camera.create_rtsp(name="Test", rtsp_url="")

    def test_create_usb_camera_negative_index_raises(self) -> None:
        """Creating a USB camera with a negative index raises ValueError."""
        with pytest.raises(ValueError, match="USB index must be a non-negative integer"):
            Camera.create_usb(name="Test", usb_index=-1)

    def test_create_camera_confidence_too_low_raises(self) -> None:
        """Confidence < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="Confidence threshold"):
            Camera.create_rtsp(
                name="Test",
                rtsp_url="rtsp://10.0.0.1/stream",
                confidence_threshold=-0.1,
            )

    def test_create_camera_confidence_too_high_raises(self) -> None:
        """Confidence > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="Confidence threshold"):
            Camera.create_rtsp(
                name="Test",
                rtsp_url="rtsp://10.0.0.1/stream",
                confidence_threshold=1.1,
            )

    def test_default_confidence_is_used(self) -> None:
        """When no confidence is specified, the default of 0.5 is used."""
        camera = Camera.create_rtsp(name="Default", rtsp_url="rtsp://10.0.0.1/stream")
        assert camera.confidence_threshold == 0.5


class TestCameraBehaviour:
    """Tests for domain behaviour methods."""

    def test_enable_camera(self) -> None:
        """Enabling a camera sets enabled to True."""
        camera = Camera.create_rtsp("Test", "rtsp://10.0.0.1/stream")
        assert camera.enabled is False
        camera.enable()
        assert camera.enabled is True

    def test_disable_camera(self) -> None:
        """Disabling a camera sets enabled to False."""
        camera = Camera.create_rtsp("Test", "rtsp://10.0.0.1/stream")
        camera.enable()
        assert camera.enabled is True
        camera.disable()
        assert camera.enabled is False

    def test_is_rtsp(self) -> None:
        """is_rtsp returns True for RTSP cameras."""
        camera = Camera.create_rtsp("Test", "rtsp://10.0.0.1/stream")
        assert camera.is_rtsp() is True
        assert camera.is_usb() is False

    def test_is_usb(self) -> None:
        """is_usb returns True for USB cameras."""
        camera = Camera.create_usb("Test", usb_index=0)
        assert camera.is_usb() is True
        assert camera.is_rtsp() is False


class TestCameraValidation:
    """Tests for Camera.validate()."""

    def test_valid_rtsp_passes(self) -> None:
        """A well-formed RTSP camera validates without error."""
        camera = Camera.create_rtsp("Valid", "rtsp://10.0.0.1/stream")
        camera.validate()  # Should not raise

    def test_valid_usb_passes(self) -> None:
        """A well-formed USB camera validates without error."""
        camera = Camera.create_usb("Valid USB", usb_index=1)
        camera.validate()  # Should not raise

    def test_validate_empty_name_raises(self) -> None:
        """A camera with an empty name fails validation."""
        camera = Camera(
            name="",
            type=CameraType.RTSP,
            rtsp_url="rtsp://10.0.0.1/stream",
        )
        with pytest.raises(ValueError, match="Camera name must not be empty"):
            camera.validate()

    def test_validate_rtsp_missing_url_raises(self) -> None:
        """An RTSP camera without a URL fails validation."""
        camera = Camera(name="Bad RTSP", type=CameraType.RTSP)
        with pytest.raises(ValueError, match="RTSP URL is required"):
            camera.validate()

    def test_validate_usb_missing_index_raises(self) -> None:
        """A USB camera without an index fails validation."""
        camera = Camera(name="Bad USB", type=CameraType.USB, usb_index=None)
        with pytest.raises(ValueError, match="USB index is required"):
            camera.validate()


class TestCameraEquality:
    """Tests for Camera equality and representation."""

    def test_cameras_with_same_id_are_equal(self) -> None:
        """Cameras with the same ID are considered equal (id is the compare field)."""
        c1 = Camera.create_rtsp("A", "rtsp://10.0.0.1/stream")
        c2 = Camera.create_rtsp("A", "rtsp://10.0.0.1/stream")
        # Both have id=None, so they compare equal on all fields
        assert c1 == c2

    def test_cameras_with_different_ids_are_equal(self) -> None:
        """Cameras with the same business fields are equal even with different IDs.

        The ``id`` field is excluded from comparison (``compare=False``)
        because domain identity is based on business keys, not DB IDs.
        """
        c1 = Camera(id=1, name="A", type=CameraType.RTSP, rtsp_url="rtsp://10.0.0.1/stream")
        c2 = Camera(id=2, name="A", type=CameraType.RTSP, rtsp_url="rtsp://10.0.0.1/stream")
        assert c1 == c2  # Same business fields: equal

    def test_camera_repr(self) -> None:
        """Camera repr includes key attributes."""
        camera = Camera.create_rtsp("Repr Test", "rtsp://10.0.0.1/stream")
        rep = repr(camera)
        assert "Repr Test" in rep
        assert "rtsp" in rep
        assert "id=None" in rep

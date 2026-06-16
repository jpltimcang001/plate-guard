"""Unit tests for CameraService.

Uses a mock repository so no database is involved.
"""

from __future__ import annotations

import pytest

from src.application.exceptions.camera_errors import (
    CameraNotFoundError,
    DuplicateNameError,
)
from src.domain.entities.camera import Camera
from src.domain.value_objects.camera_type import CameraType
from src.services.camera_service import CameraService


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def camera_service(mock_camera_repo, mock_usb_enumerator) -> CameraService:
    """Build a CameraService with a mock repo and mock USB enumerator."""
    return CameraService(
        camera_repository=mock_camera_repo,
        usb_enumerator=mock_usb_enumerator,
    )


@pytest.fixture
def camera_service_no_usb(mock_camera_repo) -> CameraService:
    """Build a CameraService with a mock repo and NO USB enumerator."""
    return CameraService(camera_repository=mock_camera_repo, usb_enumerator=None)


# ------------------------------------------------------------------
# Add Camera
# ------------------------------------------------------------------


class TestAddCamera:
    """Tests for ``CameraService.add_camera``."""

    def test_add_rtsp_camera_success(self, camera_service: CameraService) -> None:
        """Adding a valid RTSP camera returns a DTO with an ID."""
        dto = camera_service.add_camera(
            name="Front Gate",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
            confidence_threshold=0.7,
        )
        assert dto.id > 0
        assert dto.name == "Front Gate"
        assert dto.camera_type == "rtsp"
        assert dto.rtsp_url == "rtsp://192.168.1.10:554/stream"
        assert dto.enabled is False
        assert dto.confidence_threshold == 0.7

    def test_add_usb_camera_success(
        self,
        camera_service: CameraService,
    ) -> None:
        """Adding a valid USB camera returns a DTO with an ID."""
        dto = camera_service.add_camera(
            name="Lobby Camera",
            camera_type=CameraType.USB,
            usb_index=0,
            confidence_threshold=0.5,
        )
        assert dto.id > 0
        assert dto.name == "Lobby Camera"
        assert dto.camera_type == "usb"
        assert dto.usb_index == 0

    def test_add_camera_duplicate_name_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Adding a camera with a duplicate name raises DuplicateNameError."""
        camera_service.add_camera(
            name="Front Gate",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
        )
        with pytest.raises(DuplicateNameError) as exc_info:
            camera_service.add_camera(
                name="Front Gate",
                camera_type=CameraType.RTSP,
                rtsp_url="rtsp://192.168.1.20:554/stream",
            )
        assert "Front Gate" in str(exc_info.value)

    def test_add_rtsp_camera_empty_url_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Adding an RTSP camera with an empty URL raises ValueError."""
        with pytest.raises(ValueError, match="RTSP URL is required"):
            camera_service.add_camera(
                name="Bad RTSP",
                camera_type=CameraType.RTSP,
                rtsp_url="",
            )

    def test_add_usb_camera_missing_index_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Adding a USB camera without an index raises ValueError."""
        with pytest.raises(ValueError, match="USB index is required"):
            camera_service.add_camera(
                name="Bad USB",
                camera_type=CameraType.USB,
                usb_index=None,
            )

    def test_add_camera_empty_name_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Adding a camera with an empty name raises ValueError."""
        with pytest.raises(ValueError, match="Camera name must not be empty"):
            camera_service.add_camera(
                name="",
                camera_type=CameraType.RTSP,
                rtsp_url="rtsp://192.168.1.10:554/stream",
            )

    def test_add_camera_threshold_out_of_range_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Adding a camera with threshold >1.0 raises ValueError."""
        with pytest.raises(ValueError, match="Confidence threshold"):
            camera_service.add_camera(
                name="Bad Threshold",
                camera_type=CameraType.RTSP,
                rtsp_url="rtsp://192.168.1.10:554/stream",
                confidence_threshold=1.5,
            )

    def test_add_usb_camera_invalid_index_with_enumerator(
        self,
        camera_service: CameraService,
    ) -> None:
        """Adding a USB camera with an invalid index raises CameraConnectionError."""
        from src.application.exceptions.camera_errors import CameraConnectionError

        with pytest.raises(CameraConnectionError, match="USB device index 99"):
            camera_service.add_camera(
                name="Missing USB",
                camera_type=CameraType.USB,
                usb_index=99,
            )

    def test_add_usb_camera_no_enumerator_skips_validation(
        self,
        camera_service_no_usb: CameraService,
    ) -> None:
        """Without a USB enumerator, index validation is skipped."""
        dto = camera_service_no_usb.add_camera(
            name="USB No Check",
            camera_type=CameraType.USB,
            usb_index=99,
        )
        assert dto.id > 0
        assert dto.usb_index == 99


# ------------------------------------------------------------------
# Edit Camera
# ------------------------------------------------------------------


class TestEditCamera:
    """Tests for ``CameraService.edit_camera``."""

    def test_edit_camera_name(self, camera_service: CameraService) -> None:
        """Editing only the name returns an updated DTO."""
        created = camera_service.add_camera(
            name="Old Name",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
        )
        updated = camera_service.edit_camera(created.id, name="New Name")
        assert updated.name == "New Name"
        assert updated.rtsp_url == "rtsp://192.168.1.10:554/stream"

    def test_edit_camera_duplicate_name_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Renaming to an existing name raises DuplicateNameError."""
        camera_service.add_camera(
            name="Camera A",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
        )
        created_b = camera_service.add_camera(
            name="Camera B",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.20:554/stream",
        )
        with pytest.raises(DuplicateNameError):
            camera_service.edit_camera(created_b.id, name="Camera A")

    def test_edit_camera_not_found_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Editing a non-existent camera raises CameraNotFoundError."""
        with pytest.raises(CameraNotFoundError):
            camera_service.edit_camera(9999, name="Ghost")

    def test_edit_camera_threshold(self, camera_service: CameraService) -> None:
        """Editing the confidence threshold is reflected in the DTO."""
        created = camera_service.add_camera(
            name="Threshold Test",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
            confidence_threshold=0.5,
        )
        updated = camera_service.edit_camera(
            created.id,
            confidence_threshold=0.9,
        )
        assert updated.confidence_threshold == 0.9

    def test_edit_camera_invalid_threshold_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Setting an out-of-range threshold raises ValueError."""
        created = camera_service.add_camera(
            name="Bad Thresh",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
        )
        with pytest.raises(ValueError):
            camera_service.edit_camera(created.id, confidence_threshold=-0.1)


# ------------------------------------------------------------------
# Delete Camera
# ------------------------------------------------------------------


class TestDeleteCamera:
    """Tests for ``CameraService.delete_camera``."""

    def test_delete_camera_success(self, camera_service: CameraService) -> None:
        """Deleting an existing camera removes it."""
        created = camera_service.add_camera(
            name="To Delete",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
        )
        camera_service.delete_camera(created.id)
        # Verify it's gone
        with pytest.raises(CameraNotFoundError):
            camera_service.get_camera(created.id)

    def test_delete_camera_not_found_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Deleting a non-existent camera raises CameraNotFoundError."""
        with pytest.raises(CameraNotFoundError):
            camera_service.delete_camera(9999)

    def test_delete_camera_then_count_drops(
        self,
        camera_service: CameraService,
    ) -> None:
        """After deletion, the total count decreases."""
        c1 = camera_service.add_camera(
            name="Cam1",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://10.0.0.1/stream",
        )
        c2 = camera_service.add_camera(
            name="Cam2",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://10.0.0.2/stream",
        )
        assert len(camera_service.get_all_cameras()) == 2
        camera_service.delete_camera(c1.id)
        assert len(camera_service.get_all_cameras()) == 1
        camera_service.delete_camera(c2.id)
        assert len(camera_service.get_all_cameras()) == 0


# ------------------------------------------------------------------
# Enable / Disable
# ------------------------------------------------------------------


class TestEnableDisable:
    """Tests for ``CameraService.enable_camera`` and ``disable_camera``."""

    def test_enable_camera(self, camera_service: CameraService) -> None:
        """Enabling a camera sets enabled=True."""
        created = camera_service.add_camera(
            name="Toggle Test",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
        )
        assert created.enabled is False
        enabled = camera_service.enable_camera(created.id)
        assert enabled.enabled is True

    def test_disable_camera(self, camera_service: CameraService) -> None:
        """Disabling a camera sets enabled=False."""
        created = camera_service.add_camera(
            name="Toggle Test 2",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://192.168.1.10:554/stream",
        )
        camera_service.enable_camera(created.id)
        disabled = camera_service.disable_camera(created.id)
        assert disabled.enabled is False

    def test_enable_not_found_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Enabling a non-existent camera raises CameraNotFoundError."""
        with pytest.raises(CameraNotFoundError):
            camera_service.enable_camera(9999)

    def test_disable_not_found_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Disabling a non-existent camera raises CameraNotFoundError."""
        with pytest.raises(CameraNotFoundError):
            camera_service.disable_camera(9999)


# ------------------------------------------------------------------
# Query
# ------------------------------------------------------------------


class TestGetCameras:
    """Tests for query methods."""

    def test_get_all_cameras_empty(self, camera_service: CameraService) -> None:
        """With no cameras, get_all returns an empty list."""
        assert camera_service.get_all_cameras() == []

    def test_get_all_cameras_multiple(
        self,
        camera_service: CameraService,
    ) -> None:
        """Multiple cameras are all returned."""
        camera_service.add_camera(
            name="A",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://10.0.0.1/stream",
        )
        camera_service.add_camera(
            name="B",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://10.0.0.2/stream",
        )
        all_cams = camera_service.get_all_cameras()
        assert len(all_cams) == 2
        names = {c.name for c in all_cams}
        assert names == {"A", "B"}

    def test_get_enabled_cameras(self, camera_service: CameraService) -> None:
        """Only enabled cameras are returned."""
        c1 = camera_service.add_camera(
            name="Enabled Cam",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://10.0.0.1/stream",
        )
        camera_service.add_camera(
            name="Disabled Cam",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://10.0.0.2/stream",
        )
        camera_service.enable_camera(c1.id)
        enabled = camera_service.get_enabled_cameras()
        assert len(enabled) == 1
        assert enabled[0].name == "Enabled Cam"

    def test_get_camera_by_id(self, camera_service: CameraService) -> None:
        """Getting a camera by ID returns the correct DTO."""
        created = camera_service.add_camera(
            name="By ID Test",
            camera_type=CameraType.RTSP,
            rtsp_url="rtsp://10.0.0.1/stream",
        )
        fetched = camera_service.get_camera(created.id)
        assert fetched.id == created.id
        assert fetched.name == "By ID Test"

    def test_get_camera_not_found_raises(
        self,
        camera_service: CameraService,
    ) -> None:
        """Getting a non-existent camera raises CameraNotFoundError."""
        with pytest.raises(CameraNotFoundError):
            camera_service.get_camera(9999)


# ------------------------------------------------------------------
# USB Enumeration
# ------------------------------------------------------------------


class TestUsbEnumeration:
    """Tests for ``CameraService.enumerate_usb_devices``."""

    def test_enumerate_with_enumerator(
        self,
        camera_service: CameraService,
    ) -> None:
        """When an enumerator is configured, devices are returned."""
        devices = camera_service.enumerate_usb_devices()
        assert len(devices) >= 2
        assert devices[0].index == 0
        assert devices[0].name == "Mock Camera 1"

    def test_enumerate_without_enumerator(
        self,
        camera_service_no_usb: CameraService,
    ) -> None:
        """Without an enumerator, an empty list is returned."""
        devices = camera_service_no_usb.enumerate_usb_devices()
        assert devices == []

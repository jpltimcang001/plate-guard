"""Integration tests for CameraRepository with real SQLite.

These tests verify that the repository correctly persists, retrieves,
and deletes ``CameraModel`` records in the database.
"""

from __future__ import annotations

import pytest

from src.database.models import CameraModel
from src.repositories.camera_repository import CameraRepository


# ======================================================================
# Tests — add
# ======================================================================


class TestCameraRepositoryAdd:
    """Tests for ``CameraRepository.add``."""

    def test_add_rtsp_camera(self, camera_repo: CameraRepository) -> None:
        """Adding an RTSP camera returns an entity with an ID."""
        camera = CameraModel(
            name="Integration RTSP",
            type="rtsp",
            rtsp_url="rtsp://192.168.1.100:554/main",
            enabled=False,
            confidence_threshold=0.6,
        )
        saved = camera_repo.add(camera)
        assert saved.id is not None and saved.id > 0
        assert saved.name == "Integration RTSP"
        assert saved.type == "rtsp"
        assert saved.rtsp_url == "rtsp://192.168.1.100:554/main"
        assert saved.enabled == 0

    def test_add_usb_camera(self, camera_repo: CameraRepository) -> None:
        """Adding a USB camera returns an entity with an ID."""
        camera = CameraModel(
            name="Integration USB",
            type="usb",
            usb_index=1,
            enabled=False,
            confidence_threshold=0.5,
        )
        saved = camera_repo.add(camera)
        assert saved.id is not None and saved.id > 0
        assert saved.type == "usb"
        assert saved.usb_index == 1

    def test_add_duplicate_name_raises_integrity_error(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """Adding a camera with a duplicate name raises an integrity error."""
        c1 = CameraModel(
            name="Unique Name",
            type="rtsp",
            rtsp_url="rtsp://10.0.0.1/stream",
            enabled=False,
            confidence_threshold=0.5,
        )
        camera_repo.add(c1)
        c2 = CameraModel(
            name="Unique Name",
            type="rtsp",
            rtsp_url="rtsp://10.0.0.2/stream",
            enabled=False,
            confidence_threshold=0.5,
        )
        with pytest.raises(Exception):  # SQLAlchemy integrity error
            camera_repo.add(c2)


# ======================================================================
# Tests — get
# ======================================================================


class TestCameraRepositoryGet:
    """Tests for retrieval methods."""

    def test_get_by_id_found(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """Getting a camera by a valid ID returns the entity."""
        camera = CameraModel(
            name="Get By ID",
            type="rtsp",
            rtsp_url="rtsp://10.0.0.1/stream",
            enabled=False,
            confidence_threshold=0.5,
        )
        saved = camera_repo.add(camera)
        fetched = camera_repo.get_by_id(saved.id)
        assert fetched is not None
        assert fetched.name == "Get By ID"

    def test_get_by_id_not_found(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """Getting a camera by an invalid ID returns None."""
        assert camera_repo.get_by_id(9999) is None

    def test_get_by_name_found(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """Getting a camera by name returns the entity."""
        camera = CameraModel(
            name="Name Query",
            type="rtsp",
            rtsp_url="rtsp://10.0.0.1/stream",
            enabled=False,
            confidence_threshold=0.5,
        )
        camera_repo.add(camera)
        fetched = camera_repo.get_by_name("Name Query")
        assert fetched is not None
        assert fetched.rtsp_url == "rtsp://10.0.0.1/stream"

    def test_get_by_name_not_found(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """Getting a camera by a non-existent name returns None."""
        assert camera_repo.get_by_name("Does Not Exist") is None

    def test_get_all(self, camera_repo: CameraRepository) -> None:
        """Getting all cameras returns all persisted entities."""
        camera_repo.add(
            CameraModel(
                name="All A",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        camera_repo.add(
            CameraModel(
                name="All B",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.2/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        camera_repo.add(
            CameraModel(
                name="All C",
                type="usb",
                usb_index=0,
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        all_cameras = camera_repo.get_all()
        assert len(all_cameras) == 3

    def test_get_enabled(self, camera_repo: CameraRepository) -> None:
        """Getting enabled cameras returns only those with enabled=True."""
        c1 = camera_repo.add(
            CameraModel(
                name="Enabled Cam",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        camera_repo.add(
            CameraModel(
                name="Disabled Cam",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.2/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        camera_repo.update_status(c1.id, True)
        enabled = camera_repo.get_enabled()
        assert len(enabled) == 1
        assert enabled[0].name == "Enabled Cam"

    def test_exists_by_name_true(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """exists_by_name returns True for an existing name."""
        camera_repo.add(
            CameraModel(
                name="Exists Test",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        assert camera_repo.exists_by_name("Exists Test") is True

    def test_exists_by_name_false(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """exists_by_name returns False for a non-existent name."""
        assert camera_repo.exists_by_name("Non Existent") is False


# ======================================================================
# Tests — update
# ======================================================================


class TestCameraRepositoryUpdate:
    """Tests for update operations."""

    def test_update_name(self, camera_repo: CameraRepository) -> None:
        """Updating a camera's name persists the change."""
        camera = camera_repo.add(
            CameraModel(
                name="Old Name",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        camera.name = "New Name"
        updated = camera_repo.update(camera)
        assert updated.name == "New Name"
        # Verify via get
        fetched = camera_repo.get_by_id(camera.id)
        assert fetched is not None
        assert fetched.name == "New Name"

    def test_update_status(self, camera_repo: CameraRepository) -> None:
        """Enabling a camera via update_status persists the change."""
        camera = camera_repo.add(
            CameraModel(
                name="Status Test",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        result = camera_repo.update_status(camera.id, True)
        assert result is True
        fetched = camera_repo.get_by_id(camera.id)
        assert fetched is not None
        assert fetched.enabled is True

    def test_update_status_not_found(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """update_status on a non-existent ID returns False."""
        assert camera_repo.update_status(9999, True) is False

    def test_update_confidence_threshold(
        self,
        camera_repo: CameraRepository,
    ) -> None:
        """Updating the confidence threshold persists the change."""
        camera = camera_repo.add(
            CameraModel(
                name="Threshold Test",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        camera_repo.update_confidence_threshold(camera.id, 0.85)
        fetched = camera_repo.get_by_id(camera.id)
        assert fetched is not None
        assert fetched.confidence_threshold == pytest.approx(0.85)


# ======================================================================
# Tests — delete
# ======================================================================


class TestCameraRepositoryDelete:
    """Tests for delete operations."""

    def test_delete_camera(self, camera_repo: CameraRepository) -> None:
        """Deleting a camera removes it from the database."""
        camera = camera_repo.add(
            CameraModel(
                name="Delete Me",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        cam_id = camera.id
        result = camera_repo.delete(cam_id)
        assert result is True
        assert camera_repo.get_by_id(cam_id) is None

    def test_delete_not_found(self, camera_repo: CameraRepository) -> None:
        """Deleting a non-existent camera returns False."""
        assert camera_repo.delete(9999) is False

    def test_delete_reduces_count(self, camera_repo: CameraRepository) -> None:
        """Deleting a camera reduces the total count."""
        camera_repo.add(
            CameraModel(
                name="Cam A",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        c2 = camera_repo.add(
            CameraModel(
                name="Cam B",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.2/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        assert camera_repo.count() == 2
        camera_repo.delete(c2.id)
        assert camera_repo.count() == 1


# ======================================================================
# Tests — count
# ======================================================================


class TestCameraRepositoryCount:
    """Tests for the count method."""

    def test_count_empty(self, camera_repo: CameraRepository) -> None:
        """An empty database returns 0."""
        assert camera_repo.count() == 0

    def test_count_after_inserts(self, camera_repo: CameraRepository) -> None:
        """Count reflects the number of inserted records."""
        camera_repo.add(
            CameraModel(
                name="C1",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.1/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        camera_repo.add(
            CameraModel(
                name="C2",
                type="rtsp",
                rtsp_url="rtsp://10.0.0.2/stream",
                enabled=False,
                confidence_threshold=0.5,
            ),
        )
        assert camera_repo.count() == 2

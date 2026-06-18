"""Integration tests for WebhookRepository.

Tests CRUD operations, camera-scoped queries, existence checks,
and bulk deletion against a real in-memory SQLite database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.database.models import WebhookModel
from src.repositories.webhook_repository import WebhookRepository

if TYPE_CHECKING:
    from src.database.models import CameraModel


# ======================================================================
# WebhookRepository — CRUD
# ======================================================================


class TestWebhookRepositoryCRUD:
    """Tests for basic add / get / update / delete operations."""

    def test_add_and_get_by_id(
        self,
        webhook_repo: WebhookRepository,
        seeded_camera: CameraModel,
    ) -> None:
        """Adding a webhook and fetching it by ID returns the same record."""
        wh = WebhookModel(
            camera_id=seeded_camera.id,
            method="POST",
            url="https://hooks.example.com/test",
            auth_type="none",
        )
        saved = webhook_repo.add(wh)
        assert saved.id is not None and saved.id > 0
        assert saved.url == "https://hooks.example.com/test"

        fetched = webhook_repo.get_by_id(saved.id)
        assert fetched is not None
        assert fetched.camera_id == seeded_camera.id
        assert fetched.method == "POST"

    def test_get_by_id_not_found(
        self,
        webhook_repo: WebhookRepository,
    ) -> None:
        """Fetching a non‑existent ID returns None."""
        assert webhook_repo.get_by_id(999_999) is None

    def test_get_all(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
    ) -> None:
        """get_all returns all persisted webhooks."""
        all_ = webhook_repo.get_all()
        assert len(all_) >= 1
        assert seeded_webhook.id in {w.id for w in all_}

    def test_delete(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
    ) -> None:
        """Deleting a webhook removes it and returns True."""
        assert webhook_repo.delete(seeded_webhook.id) is True
        assert webhook_repo.get_by_id(seeded_webhook.id) is None

    def test_delete_not_found(
        self,
        webhook_repo: WebhookRepository,
    ) -> None:
        """Deleting a non‑existent ID returns False."""
        assert webhook_repo.delete(999_999) is False

    def test_exists_true(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
    ) -> None:
        """exists returns True for an existing webhook."""
        assert webhook_repo.exists(seeded_webhook.id) is True

    def test_exists_false(
        self,
        webhook_repo: WebhookRepository,
    ) -> None:
        """exists returns False for a non‑existent webhook."""
        assert webhook_repo.exists(999_999) is False

    def test_count_empty(
        self,
        webhook_repo: WebhookRepository,
    ) -> None:
        """count returns 0 when no webhooks exist."""
        assert webhook_repo.count() == 0

    def test_count_after_insert(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
    ) -> None:
        """count reflects the number of persisted webhooks."""
        assert webhook_repo.count() >= 1

    def test_update(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
    ) -> None:
        """Updating a webhook persists the changes."""
        seeded_webhook.url = "https://updated.example.com/hook"
        updated = webhook_repo.update(seeded_webhook)
        assert updated.url == "https://updated.example.com/hook"
        # Verify in a fresh fetch
        fetched = webhook_repo.get_by_id(seeded_webhook.id)
        assert fetched is not None
        assert fetched.url == "https://updated.example.com/hook"


# ======================================================================
# WebhookRepository — Camera-scoped queries
# ======================================================================


class TestWebhookRepositoryCameraScoped:
    """Tests for get_by_camera_id, delete_by_camera_id, has_webhooks."""

    def test_get_by_camera_id(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
        seeded_camera: CameraModel,
    ) -> None:
        """get_by_camera_id returns all webhooks for a given camera."""
        result = webhook_repo.get_by_camera_id(seeded_camera.id)
        assert len(result) >= 1
        assert all(w.camera_id == seeded_camera.id for w in result)

    def test_get_by_camera_id_no_webhooks(
        self,
        webhook_repo: WebhookRepository,
    ) -> None:
        """get_by_camera_id returns an empty list when no webhooks exist."""
        assert webhook_repo.get_by_camera_id(999) == []

    def test_get_by_camera_id_other_camera_not_included(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
        seeded_camera: CameraModel,
    ) -> None:
        """Webhooks for one camera do not appear in another camera's list."""
        # A second camera with no webhooks
        from src.database.models import CameraModel as CM

        cam2 = CM(
            name="Other Camera",
            type="usb",
            usb_index=2,
            enabled=True,
        )
        from src.repositories.camera_repository import CameraRepository

        cam2 = CameraRepository(
            webhook_repo._session_manager  # type: ignore[attr-defined]
        ).add(cam2)

        result = webhook_repo.get_by_camera_id(cam2.id)
        assert result == []

    def test_has_webhooks_true(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
        seeded_camera: CameraModel,
    ) -> None:
        """has_webhooks returns True when webhooks exist for the camera."""
        assert webhook_repo.has_webhooks(seeded_camera.id) is True

    def test_has_webhooks_false(
        self,
        webhook_repo: WebhookRepository,
    ) -> None:
        """has_webhooks returns False when no webhooks exist."""
        assert webhook_repo.has_webhooks(404) is False

    def test_delete_by_camera_id(
        self,
        webhook_repo: WebhookRepository,
        seeded_webhook: WebhookModel,
        seeded_camera: CameraModel,
    ) -> None:
        """delete_by_camera_id removes all webhooks for a camera."""
        # Insert a second webhook for the same camera
        wh2 = WebhookModel(
            camera_id=seeded_camera.id,
            method="PUT",
            url="https://hooks.example.com/other",
            auth_type="bearer",
            auth_value="token-xyz",
        )
        webhook_repo.add(wh2)

        deleted = webhook_repo.delete_by_camera_id(seeded_camera.id)
        assert deleted >= 2
        assert webhook_repo.get_by_camera_id(seeded_camera.id) == []

    def test_delete_by_camera_id_noop(
        self,
        webhook_repo: WebhookRepository,
    ) -> None:
        """delete_by_camera_id returns 0 when no webhooks match."""
        assert webhook_repo.delete_by_camera_id(404) == 0

    def test_webhook_with_auth_details(
        self,
        webhook_repo: WebhookRepository,
        seeded_camera: CameraModel,
    ) -> None:
        """A webhook with bearer auth and custom headers is stored/retrieved."""
        wh = WebhookModel(
            camera_id=seeded_camera.id,
            method="POST",
            url="https://api.example.com/webhook",
            headers_json='{"X-Custom": "value"}',
            auth_type="bearer",
            auth_value="my-secret-token",
            body_template='{"plate": "{{plate}}"}',
            send_image=True,
            send_video=True,
        )
        saved = webhook_repo.add(wh)
        fetched = webhook_repo.get_by_id(saved.id)
        assert fetched is not None
        assert fetched.auth_type == "bearer"
        assert fetched.auth_value == "my-secret-token"
        assert fetched.send_image is True
        assert fetched.send_video is True
        assert fetched.body_template == '{"plate": "{{plate}}"}'

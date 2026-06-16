"""Unit tests for webhook entities, client, and service.

All HTTP interactions are mocked so no network access is required.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, PropertyMock, call, patch

import httpx
import numpy as np
import pytest

from src.detection.detection_result import DetectionResult
from src.domain.events.plate_detected import PlateDetected
from src.webhook.webhook_client import WebhookClient, WebhookConfig, WebhookError
from src.webhook.webhook_payload import WebhookPayload, WebhookResult
from src.webhook.webhook_service import WebhookService

# ======================================================================
# Helpers
# ======================================================================


def _make_mock_response(
    status_code: int = 200,
    text: str = "OK",
) -> MagicMock:
    """Return a mock ``httpx.Response``."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    return resp


def _make_detection_event(
    camera_id: int = 1,
    confidence: float = 0.95,
) -> PlateDetected:
    """Return a minimal ``PlateDetected`` event."""
    return PlateDetected(
        camera_id=camera_id,
        bounding_box=(50, 60, 200, 150),
        confidence=confidence,
        timestamp=datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_detection_result() -> DetectionResult:
    """Return a sample ``DetectionResult``."""
    return DetectionResult(
        bounding_box=(50, 60, 200, 150),
        confidence=0.95,
        class_id=0,
        class_name="plate",
    )


def _make_mock_webhook_model(
    webhook_id: int = 1,
    camera_id: int = 1,
    method: str = "POST",
    url: str = "https://example.com/hook",
    auth_type: str = "none",
    auth_value: str = "",
    headers_json: Optional[str] = None,
    send_image: bool = False,
    send_video: bool = False,
) -> MagicMock:
    """Return a mock ORM ``WebhookModel``."""
    m = MagicMock()
    m.id = webhook_id
    m.camera_id = camera_id
    m.method = method
    m.url = url
    m.headers_json = headers_json
    m.auth_type = auth_type
    m.auth_value = auth_value
    m.body_template = ""
    m.send_image = send_image
    m.send_video = send_video
    return m


# ======================================================================
# WebhookPayload
# ======================================================================


class TestWebhookPayload:
    """Tests for the WebhookPayload entity."""

    def test_create_default(self) -> None:
        """Default payload has plate_detected event type."""
        p = WebhookPayload()
        assert p.event_type == "plate_detected"
        assert p.camera_id == 0
        assert p.plate_text == ""
        assert not p.has_image
        assert not p.has_video

    def test_create_with_values(self) -> None:
        """Payload stores all constructor values."""
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        p = WebhookPayload(
            event_type="test_event",
            camera_id=5,
            plate_text="ABC123",
            detection_confidence=0.95,
            ocr_confidence=0.92,
            timestamp=datetime(2026, 1, 1),
            snapshot_image=img,
            video_bytes=b"fake_video_data",
            metadata={"extra": "value"},
        )
        assert p.event_type == "test_event"
        assert p.camera_id == 5
        assert p.plate_text == "ABC123"
        assert p.detection_confidence == 0.95
        assert p.has_image
        assert p.has_video
        assert p.metadata["extra"] == "value"

    def test_has_image_false_when_none(self) -> None:
        """has_image is False when snapshot is None."""
        p = WebhookPayload()
        assert not p.has_image

    def test_has_image_false_when_empty(self) -> None:
        """has_image is False when snapshot is an empty array."""
        p = WebhookPayload(snapshot_image=np.array([], dtype=np.uint8))
        assert not p.has_image

    def test_has_video_false_when_none(self) -> None:
        """has_video is False when video_bytes is None."""
        p = WebhookPayload()
        assert not p.has_video

    def test_has_video_false_when_empty_bytes(self) -> None:
        """has_video is False when video_bytes is empty."""
        p = WebhookPayload(video_bytes=b"")
        assert not p.has_video

    def test_to_json_dict_includes_fields(self) -> None:
        """to_json_dict returns expected keys."""
        ts = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        p = WebhookPayload(
            event_type="plate_detected",
            camera_id=3,
            plate_text="XYZ789",
            detection_confidence=0.88,
            ocr_confidence=0.85,
            timestamp=ts,
            metadata={"bbox": "10,20,100,80"},
        )
        d = p.to_json_dict()
        assert d["event"] == "plate_detected"
        assert d["camera_id"] == 3
        assert d["plate"] == "XYZ789"
        assert d["detection_confidence"] == 0.88
        assert d["ocr_confidence"] == 0.85
        assert d["timestamp"] == "2026-06-15T12:00:00+00:00"
        assert d["bbox"] == "10,20,100,80"

    def test_to_json_dict_excludes_image_data(self) -> None:
        """to_json_dict does not include raw image or video."""
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        p = WebhookPayload(
            snapshot_image=img,
            video_bytes=b"data",
        )
        d = p.to_json_dict()
        assert "snapshot_image" not in d
        assert "video_bytes" not in d
        assert d["has_image"] is True
        assert d["has_video"] is True

    def test_to_json_dict_includes_metadata(self) -> None:
        """to_json_dict merges metadata into the top-level dict."""
        p = WebhookPayload(metadata={"custom_key": "custom_val"})
        d = p.to_json_dict()
        assert d["custom_key"] == "custom_val"


# ======================================================================
# WebhookResult
# ======================================================================


class TestWebhookResult:
    """Tests for the WebhookResult entity."""

    def test_create_default(self) -> None:
        """Default result has zero values and is not successful."""
        r = WebhookResult()
        assert r.webhook_id == 0
        assert r.url == ""
        assert r.status_code == 0
        assert not r.success

    def test_create_success(self) -> None:
        """A 200 response creates a successful result."""
        r = WebhookResult(
            webhook_id=1,
            url="https://example.com/hook",
            status_code=200,
            success=True,
            attempt=1,
            total_attempts=1,
            elapsed_ms=45.2,
        )
        assert r.success
        assert r.status_code == 200
        assert "ok" in repr(r)

    def test_create_failure(self) -> None:
        """A 500 response creates a failed result."""
        r = WebhookResult(
            webhook_id=2,
            url="https://example.com/hook",
            status_code=500,
            success=False,
            attempt=3,
            total_attempts=3,
            error_message="Internal server error",
        )
        assert not r.success
        assert r.status_code == 500
        assert "fail" in repr(r)
        assert "3/3" in repr(r)


# ======================================================================
# WebhookClient — authentication
# ======================================================================


class TestWebhookClientAuth:
    """Tests for auth header generation."""

    def test_auth_none_returns_empty(self) -> None:
        """Auth type 'none' returns no headers."""
        config = WebhookConfig(auth_type="none")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert headers == {}

    def test_auth_basic_encodes_credentials(self) -> None:
        """Auth type 'basic' produces a Basic Authorization header."""
        config = WebhookConfig(auth_type="basic", auth_value="user:pass")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert "authorization" in headers
        assert headers["authorization"].startswith("Basic ")
        # base64("user:pass") = "dXNlcjpwYXNz"
        assert headers["authorization"] == "Basic dXNlcjpwYXNz"

    def test_auth_basic_empty_value_warns(self) -> None:
        """Auth type 'basic' with empty value returns no headers."""
        config = WebhookConfig(auth_type="basic", auth_value="")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert headers == {}

    def test_auth_bearer_returns_token_header(self) -> None:
        """Auth type 'bearer' produces a Bearer Authorization header."""
        config = WebhookConfig(auth_type="bearer", auth_value="my-token")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert headers["authorization"] == "Bearer my-token"

    def test_auth_bearer_empty_value_warns(self) -> None:
        """Auth type 'bearer' with empty value returns no headers."""
        config = WebhookConfig(auth_type="bearer", auth_value="")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert headers == {}

    def test_auth_api_key_returns_header(self) -> None:
        """Auth type 'api_key' produces an X-API-Key header."""
        config = WebhookConfig(auth_type="api_key", auth_value="key-123")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert headers["x-api-key"] == "key-123"

    def test_auth_api_key_empty_value_warns(self) -> None:
        """Auth type 'api_key' with empty value returns no headers."""
        config = WebhookConfig(auth_type="api_key", auth_value="")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert headers == {}

    def test_auth_unknown_type_returns_empty(self) -> None:
        """Unknown auth type is treated as 'none'."""
        config = WebhookConfig(auth_type="oauth", auth_value="token")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert headers == {}

    def test_auth_case_insensitive(self) -> None:
        """Auth type matching is case-insensitive."""
        config = WebhookConfig(auth_type="BEARER", auth_value="tok")
        client = WebhookClient()
        headers = client._build_auth_headers(config)
        assert headers["authorization"] == "Bearer tok"


# ======================================================================
# WebhookClient — retry logic
# ======================================================================


class TestWebhookClientRetry:
    """Tests for the retry decision logic."""

    def test_no_retry_on_success(self) -> None:
        """A successful result should not be retried."""
        client = WebhookClient(max_attempts=3)
        result = WebhookResult(success=True, status_code=200)
        assert not client._should_retry(result, attempt=1)

    def test_no_retry_on_4xx(self) -> None:
        """A 4xx client error should not be retried."""
        client = WebhookClient()
        result = WebhookResult(success=False, status_code=404)
        assert not client._should_retry(result, attempt=1)

    def test_retry_on_5xx(self) -> None:
        """A 5xx server error should be retried."""
        client = WebhookClient()
        result = WebhookResult(success=False, status_code=500)
        assert client._should_retry(result, attempt=1)

    def test_retry_on_429(self) -> None:
        """A 429 rate-limit response should be retried."""
        client = WebhookClient()
        result = WebhookResult(success=False, status_code=429)
        assert client._should_retry(result, attempt=1)

    def test_retry_on_408(self) -> None:
        """A 408 timeout response should be retried."""
        client = WebhookClient()
        result = WebhookResult(success=False, status_code=408)
        assert client._should_retry(result, attempt=1)

    def test_retry_on_network_error(self) -> None:
        """A network error (status 0) should be retried."""
        client = WebhookClient()
        result = WebhookResult(
            success=False,
            status_code=0,
            error_message="Connection refused",
        )
        assert client._should_retry(result, attempt=1)

    def test_no_retry_on_last_attempt(self) -> None:
        """No retry when the max attempt count is reached."""
        client = WebhookClient(max_attempts=3)
        result = WebhookResult(success=False, status_code=500)
        assert not client._should_retry(result, attempt=3)


# ======================================================================
# WebhookClient — HTTP sending
# ======================================================================


class TestWebhookClientSend:
    """Tests for the send method with a mock HTTP client."""

    def test_send_post_json_success(self) -> None:
        """A POST with JSON payload succeeds on 200."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _make_mock_response(200, '{"ok": true}')
        client = WebhookClient(client=mock_http, max_attempts=1)

        config = WebhookConfig(method="POST", url="https://example.com/hook")
        payload = WebhookPayload(plate_text="ABC123")
        result = client.send(config, payload)

        assert result.success
        assert result.status_code == 200
        assert result.webhook_id == 0
        mock_http.request.assert_called_once()

    def test_send_get_query_params(self) -> None:
        """A GET request sends payload data as query params."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = _make_mock_response(200)
        client = WebhookClient(client=mock_http, max_attempts=1)

        config = WebhookConfig(method="GET", url="https://example.com/hook")
        payload = WebhookPayload(plate_text="ABC123", camera_id=5)
        result = client.send(config, payload)

        assert result.success
        # Verify query params were passed
        _call_kwargs = mock_http.get.call_args[1]
        assert "params" in _call_kwargs
        assert _call_kwargs["params"]["plate"] == "ABC123"
        assert _call_kwargs["params"]["camera_id"] == "5"

    def test_send_put_json(self) -> None:
        """A PUT request sends JSON payload."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _make_mock_response(200)
        client = WebhookClient(client=mock_http, max_attempts=1)

        config = WebhookConfig(method="PUT", url="https://example.com/hook")
        payload = WebhookPayload(plate_text="XYZ789")
        result = client.send(config, payload)

        assert result.success
        _call_kwargs = mock_http.request.call_args
        assert _call_kwargs[0][0] == "PUT"
        assert _call_kwargs[1]["json"]["plate"] == "XYZ789"

    def test_send_patch_json(self) -> None:
        """A PATCH request sends JSON payload."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _make_mock_response(200)
        client = WebhookClient(client=mock_http, max_attempts=1)

        config = WebhookConfig(method="PATCH", url="https://example.com/hook")
        payload = WebhookPayload(plate_text="PATCHED")
        result = client.send(config, payload)

        assert result.success
        _call = mock_http.request.call_args
        assert _call[0][0] == "PATCH"

    def test_send_invalid_method_raises(self) -> None:
        """An unsupported HTTP method raises WebhookError."""
        client = WebhookClient()
        config = WebhookConfig(method="DELETE", url="https://example.com/hook")
        payload = WebhookPayload()
        with pytest.raises(WebhookError, match="Unsupported HTTP method"):
            client.send(config, payload)

    def test_send_retry_on_500_then_succeed(self) -> None:
        """A 500 response is retried and succeeds on the second attempt."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            _make_mock_response(500, "Server Error"),
            _make_mock_response(200, "OK"),
        ]
        client = WebhookClient(client=mock_http, max_attempts=3)

        # Override sleep to avoid real waits
        client._sleep = lambda delay: None  # type: ignore[method-assign]

        config = WebhookConfig(method="POST", url="https://example.com/hook")
        payload = WebhookPayload()
        result = client.send(config, payload)

        assert result.success
        assert result.status_code == 200
        assert result.attempt == 2
        assert mock_http.request.call_count == 2

    def test_send_retry_on_network_error_then_succeed(self) -> None:
        """A network error is retried."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            httpx.ConnectError("Connection refused"),
            _make_mock_response(200, "OK"),
        ]
        client = WebhookClient(client=mock_http, max_attempts=3)
        client._sleep = lambda delay: None  # type: ignore[method-assign]

        config = WebhookConfig(method="POST", url="https://example.com/hook")
        payload = WebhookPayload()
        result = client.send(config, payload)

        assert result.success
        assert result.attempt == 2

    def test_send_exhausts_retries_on_500(self) -> None:
        """Repeated 500 errors exhaust retries."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _make_mock_response(500, "Error")
        client = WebhookClient(client=mock_http, max_attempts=3)
        client._sleep = lambda delay: None  # type: ignore[method-assign]

        config = WebhookConfig(method="POST", url="https://example.com/hook")
        payload = WebhookPayload()
        result = client.send(config, payload)

        assert not result.success
        assert result.attempt == 3
        assert mock_http.request.call_count == 3

    def test_send_does_not_retry_4xx(self) -> None:
        """A 404 response is not retried."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _make_mock_response(404, "Not Found")
        client = WebhookClient(client=mock_http, max_attempts=3)

        config = WebhookConfig(method="POST", url="https://example.com/hook")
        payload = WebhookPayload()
        result = client.send(config, payload)

        assert not result.success
        assert result.status_code == 404
        assert mock_http.request.call_count == 1

    def test_send_with_basic_auth(self) -> None:
        """Auth headers are included in the request."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _make_mock_response(200)
        client = WebhookClient(client=mock_http, max_attempts=1)

        config = WebhookConfig(
            method="POST",
            url="https://example.com/hook",
            auth_type="bearer",
            auth_value="my-token",
        )
        payload = WebhookPayload()
        client.send(config, payload)

        _call_headers = mock_http.request.call_args[1]["headers"]
        assert _call_headers["authorization"] == "Bearer my-token"


# ======================================================================
# WebhookService — build_payload
# ======================================================================


class TestWebhookServiceBuildPayload:
    """Tests for ``WebhookService.build_payload``."""

    def test_build_minimal(self) -> None:
        """build_payload with just an event produces valid payload."""
        service = WebhookService(
            webhook_repository=MagicMock(),
            detection_repository=MagicMock(),
        )
        event = _make_detection_event(camera_id=7, confidence=0.9)
        payload = service.build_payload(event)

        assert payload.event_type == "plate_detected"
        assert payload.camera_id == 7
        assert payload.detection_confidence == 0.9
        assert payload.plate_text == ""

    def test_build_with_ocr(self) -> None:
        """build_payload includes OCR results."""
        service = WebhookService(
            webhook_repository=MagicMock(),
            detection_repository=MagicMock(),
        )
        event = _make_detection_event()
        payload = service.build_payload(
            event,
            ocr_text="ABC123",
            ocr_confidence=0.92,
        )
        assert payload.plate_text == "ABC123"
        assert payload.ocr_confidence == 0.92

    def test_build_with_detection_result(self) -> None:
        """build_payload includes bounding box from DetectionResult."""
        service = WebhookService(
            webhook_repository=MagicMock(),
            detection_repository=MagicMock(),
        )
        event = _make_detection_event()
        det = _make_detection_result()
        payload = service.build_payload(event, detection_result=det)

        assert payload.metadata["bbox_x1"] == 50
        assert payload.metadata["bbox_y1"] == 60
        assert payload.metadata["bbox_x2"] == 200
        assert payload.metadata["bbox_y2"] == 150
        assert payload.metadata["bbox_width"] == 150
        assert payload.metadata["bbox_height"] == 90

    def test_build_with_image_and_video(self) -> None:
        """build_payload attaches snapshot and video."""
        service = WebhookService(
            webhook_repository=MagicMock(),
            detection_repository=MagicMock(),
        )
        event = _make_detection_event()
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        payload = service.build_payload(
            event,
            snapshot_image=img,
            video_bytes=b"video_data",
        )
        assert payload.has_image
        assert payload.has_video

    def test_build_with_metadata(self) -> None:
        """build_payload merges custom metadata."""
        service = WebhookService(
            webhook_repository=MagicMock(),
            detection_repository=MagicMock(),
        )
        event = _make_detection_event()
        payload = service.build_payload(
            event,
            metadata={"zone": "entry", "site": "main"},
        )
        assert payload.metadata["zone"] == "entry"
        assert payload.metadata["site"] == "main"


# ======================================================================
# WebhookService — deliver
# ======================================================================


class TestWebhookServiceDeliver:
    """Tests for ``WebhookService.deliver`` and ``deliver_batch``."""

    def _make_service(
        self,
        webhooks: Optional[List[MagicMock]] = None,
    ) -> WebhookService:
        """Build a WebhookService with mocked dependencies."""
        mock_webhook_repo = MagicMock()
        if webhooks is not None:
            mock_webhook_repo.get_by_camera_id.return_value = webhooks
        else:
            mock_webhook_repo.get_by_camera_id.return_value = []

        mock_detection_repo = MagicMock()
        mock_client = MagicMock(spec=WebhookClient)
        mock_client.send.return_value = WebhookResult(
            webhook_id=1,
            url="https://example.com/hook",
            status_code=200,
            success=True,
            attempt=1,
            total_attempts=1,
        )

        return WebhookService(
            webhook_repository=mock_webhook_repo,
            detection_repository=mock_detection_repo,
            client=mock_client,
        )

    def test_deliver_no_webhooks(self) -> None:
        """deliver returns empty list when no webhooks configured."""
        service = self._make_service(webhooks=[])
        payload = WebhookPayload()
        results = service.deliver(camera_id=1, payload=payload)
        assert results == []

    def test_deliver_single_webhook(self) -> None:
        """deliver sends to a single webhook and returns its result."""
        wh = _make_mock_webhook_model(webhook_id=10)
        service = self._make_service(webhooks=[wh])
        payload = WebhookPayload(plate_text="ABC")

        results = service.deliver(camera_id=1, payload=payload)

        assert len(results) == 1
        assert results[0].success

        # Verify the client received the correct config
        _call_config: WebhookConfig = service._client.send.call_args[0][0]
        assert _call_config.webhook_id == 10
        assert _call_config.url == "https://example.com/hook"
        assert _call_config.method == "POST"

    def test_deliver_multiple_webhooks(self) -> None:
        """deliver sends to all webhooks for the camera."""
        wh1 = _make_mock_webhook_model(webhook_id=1, url="https://hook1")
        wh2 = _make_mock_webhook_model(webhook_id=2, url="https://hook2")
        service = self._make_service(webhooks=[wh1, wh2])
        payload = WebhookPayload()

        results = service.deliver(camera_id=1, payload=payload)

        assert len(results) == 2

    def test_deliver_updates_detection_status_on_success(self) -> None:
        """deliver updates detection status to 'success' when all OK."""
        wh = _make_mock_webhook_model(webhook_id=1)
        service = self._make_service(webhooks=[wh])
        payload = WebhookPayload()

        service.deliver(camera_id=1, payload=payload, detection_id=42)

        service._detection_repo.update_webhook_status.assert_called_once_with(
            detection_id=42,
            status="success",
        )

    def test_deliver_updates_detection_status_on_failure(self) -> None:
        """deliver updates detection status to 'failed' on error."""
        wh = _make_mock_webhook_model(webhook_id=1)
        service = self._make_service(webhooks=[wh])
        # Make the client return a failure
        service._client.send.return_value = WebhookResult(
            webhook_id=1,
            status_code=500,
            success=False,
            attempt=3,
            total_attempts=3,
            error_message="Server error",
        )
        payload = WebhookPayload()

        service.deliver(camera_id=1, payload=payload, detection_id=42)

        service._detection_repo.update_webhook_status.assert_called_once_with(
            detection_id=42,
            status="failed",
        )

    def test_deliver_without_detection_id_skips_update(self) -> None:
        """deliver does not update detection status when no ID given."""
        wh = _make_mock_webhook_model(webhook_id=1)
        service = self._make_service(webhooks=[wh])
        payload = WebhookPayload()

        service.deliver(camera_id=1, payload=payload)

        service._detection_repo.update_webhook_status.assert_not_called()

    def test_deliver_batch_with_multiple_cameras(self) -> None:
        """deliver_batch sends to all webhooks for multiple cameras."""
        wh = _make_mock_webhook_model(webhook_id=1)
        mock_webhook_repo = MagicMock()
        mock_webhook_repo.get_by_camera_id.return_value = [wh]
        mock_client = MagicMock(spec=WebhookClient)
        mock_client.send.return_value = WebhookResult(
            webhook_id=1, status_code=200, success=True, attempt=1, total_attempts=1,
        )

        service = WebhookService(
            webhook_repository=mock_webhook_repo,
            detection_repository=MagicMock(),
            client=mock_client,
        )

        payload = WebhookPayload()
        results = service.deliver_batch(
            camera_ids={1, 2},
            payload=payload,
        )

        assert len(results) == 2
        assert 1 in results
        assert 2 in results
        assert mock_webhook_repo.get_by_camera_id.call_count == 2


# ======================================================================
# WebhookService — model_to_config
# ======================================================================


class TestWebhookServiceModelToConfig:
    """Tests for the internal ``_model_to_config`` conversion."""

    def test_convert_basic(self) -> None:
        """Basic conversion preserves all fields."""
        wh = _make_mock_webhook_model(
            webhook_id=5,
            camera_id=2,
            method="PUT",
            url="https://example.com/api",
            auth_type="bearer",
            auth_value="tok123",
            send_image=True,
        )
        service = WebhookService(
            webhook_repository=MagicMock(),
            detection_repository=MagicMock(),
        )
        payload = WebhookPayload()
        config = service._model_to_config(wh, payload)

        assert config.webhook_id == 5
        assert config.method == "PUT"
        assert config.url == "https://example.com/api"
        assert config.auth_type == "bearer"
        assert config.auth_value == "tok123"
        assert config.send_image is True
        assert config.send_video is False

    def test_convert_headers_json_parsed(self) -> None:
        """headers_json is parsed into a dict."""
        wh = _make_mock_webhook_model(
            webhook_id=1,
            headers_json='{"X-Custom": "value1", "X-Other": "value2"}',
        )
        service = WebhookService(
            webhook_repository=MagicMock(),
            detection_repository=MagicMock(),
        )
        config = service._model_to_config(wh, WebhookPayload())

        assert config.headers["X-Custom"] == "value1"
        assert config.headers["X-Other"] == "value2"

    def test_convert_invalid_headers_json_does_not_crash(self) -> None:
        """Invalid headers_json is handled gracefully."""
        wh = _make_mock_webhook_model(
            webhook_id=1,
            headers_json="not valid json",
        )
        service = WebhookService(
            webhook_repository=MagicMock(),
            detection_repository=MagicMock(),
        )
        config = service._model_to_config(wh, WebhookPayload())
        assert config.headers == {}

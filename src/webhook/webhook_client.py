"""Low-level HTTP client for webhook delivery with auth, retry, and file upload."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
from loguru import logger

from src.webhook.webhook_payload import WebhookPayload, WebhookResult


class WebhookError(Exception):
    """Raised when a webhook delivery fails irrecoverably."""


@dataclass
class WebhookConfig:
    """Normalised configuration for a single webhook target.

    This is a plain-data representation of the relevant fields from
    ``WebhookModel`` so the client has no dependency on the ORM.

    Attributes:
        webhook_id: Database primary key (for tracking).
        method: HTTP method (``"GET"``, ``"POST"``, ``"PUT"``,
            ``"PATCH"``).
        url: Target URL.
        headers: Custom HTTP headers as a dict.
        auth_type: Authentication scheme (``"none"``, ``"basic"``,
            ``"bearer"``, ``"api_key"``).
        auth_value: Credential (token, ``"user:pass"``, or key value).
        body_template: Optional JSON template string.
        send_image: Whether to attach the snapshot image.
        send_video: Whether to attach the video clip.
    """

    webhook_id: int = 0
    method: str = "POST"
    url: str = ""
    headers: Dict[str, str] = None  # type: ignore[assignment]
    auth_type: str = "none"
    auth_value: str = ""
    body_template: str = ""
    send_image: bool = False
    send_video: bool = False

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}


class WebhookClient:
    """Low-level HTTP client that sends webhook requests.

    Handles:
    - GET / POST / PUT / PATCH methods
    - None / Basic / Bearer / API-Key authentication
    - Custom headers
    - Image and video upload via multipart/form-data
    - Retry with exponential backoff (3 attempts)
    - Timeout and error handling
    """

    VALID_METHODS = frozenset({"GET", "POST", "PUT", "PATCH"})
    RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
    MAX_ATTEMPTS = 3
    BASE_TIMEOUT_SECONDS = 30.0
    BACKOFF_FACTOR = 2.0
    INITIAL_BACKOFF_SECONDS = 1.0

    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        max_attempts: int = MAX_ATTEMPTS,
        base_timeout: float = BASE_TIMEOUT_SECONDS,
    ) -> None:
        """Initialise the webhook client.

        Args:
            client: An optional ``httpx.Client`` for dependency
                injection (e.g. with a mock client in tests).
            max_attempts: Maximum delivery attempts (default 3).
            base_timeout: Request timeout in seconds (default 30).

        """
        self._client = client
        self._max_attempts = max_attempts
        self._base_timeout = base_timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(
        self,
        config: WebhookConfig,
        payload: WebhookPayload,
    ) -> WebhookResult:
        """Deliver a webhook payload according to the given config.

        Implements retry with exponential backoff.  Only retries on
        network errors, timeouts, and retryable HTTP status codes
        (408, 429, 5xx).

        Args:
            config: Target webhook configuration.
            payload: The payload to deliver.

        Returns:
            A ``WebhookResult`` summarising the outcome.

        """
        method = config.method.upper()
        if method not in self.VALID_METHODS:
            raise WebhookError(
                f"Unsupported HTTP method: {config.method!r}",
            )

        last_result: Optional[WebhookResult] = None

        for attempt in range(1, self._max_attempts + 1):
            result = self._try_send(config, payload, attempt)
            last_result = result

            if result.success:
                logger.info(
                    "Webhook {} delivered (id={}, url={!r}, attempt={}/{})",
                    method,
                    config.webhook_id,
                    config.url,
                    attempt,
                    self._max_attempts,
                )
                return result

            # Decide whether to retry
            if not self._should_retry(result, attempt):
                logger.warning(
                    "Webhook {} failed (id={}, url={!r}, attempt={}/{}, "
                    "status={}, error={!r})",
                    method,
                    config.webhook_id,
                    config.url,
                    attempt,
                    self._max_attempts,
                    result.status_code,
                    result.error_message,
                )
                return result

            # Exponential backoff
            if attempt < self._max_attempts:
                delay = self.INITIAL_BACKOFF_SECONDS * (
                    self.BACKOFF_FACTOR ** (attempt - 1)
                )
                logger.debug(
                    "Retrying webhook {} (id={}) in {:.1f}s "
                    "(attempt {}/{})",
                    method,
                    config.webhook_id,
                    delay,
                    attempt + 1,
                    self._max_attempts,
                )
                self._sleep(delay)

        # Exhausted retries
        assert last_result is not None
        logger.error(
            "Webhook {} exhausted retries (id={}, url={!r})",
            method,
            config.webhook_id,
            config.url,
        )
        return last_result

    # ------------------------------------------------------------------
    # Internal: single attempt
    # ------------------------------------------------------------------

    def _try_send(
        self,
        config: WebhookConfig,
        payload: WebhookPayload,
        attempt: int,
    ) -> WebhookResult:
        """Execute a single webhook delivery attempt.

        Args:
            config: Target webhook configuration.
            payload: The payload to deliver.
            attempt: Which attempt number (1-indexed).

        Returns:
            A ``WebhookResult`` for this attempt.

        """
        method = config.method.upper()
        url = config.url
        start = time.perf_counter()

        try:
            client = self._get_client()

            # Build auth headers
            auth_headers = self._build_auth_headers(config)

            # Merge custom headers
            request_headers: Dict[str, str] = {}
            request_headers.update(auth_headers)
            request_headers.update(config.headers)

            has_files = (config.send_image and payload.has_image) or (
                config.send_video and payload.has_video
            )

            if method == "GET":
                # GET requests send data as query params
                json_data = payload.to_json_dict()
                query_params: Dict[str, str] = {
                    k: json.dumps(v) if not isinstance(v, str) else v
                    for k, v in json_data.items()
                }
                response = client.get(
                    url,
                    headers=request_headers,
                    params=query_params,
                    timeout=self._base_timeout,
                )
            elif has_files:
                response = self._send_multipart(
                    client, method, url, request_headers, config, payload,
                )
            else:
                # Plain JSON
                json_data = payload.to_json_dict()
                request_headers.setdefault("content-type", "application/json")
                response = client.request(
                    method,
                    url,
                    headers=request_headers,
                    json=json_data,
                    timeout=self._base_timeout,
                )

            elapsed_ms = (time.perf_counter() - start) * 1000.0

            return WebhookResult(
                webhook_id=config.webhook_id,
                url=url,
                status_code=response.status_code,
                success=200 <= response.status_code < 300,
                attempt=attempt,
                total_attempts=self._max_attempts,
                response_body=response.text[:500],
                elapsed_ms=round(elapsed_ms, 1),
            )

        except httpx.TimeoutException as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return WebhookResult(
                webhook_id=config.webhook_id,
                url=url,
                status_code=0,
                success=False,
                attempt=attempt,
                total_attempts=self._max_attempts,
                error_message=f"Request timed out: {exc}",
                elapsed_ms=round(elapsed_ms, 1),
            )

        except httpx.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return WebhookResult(
                webhook_id=config.webhook_id,
                url=url,
                status_code=0,
                success=False,
                attempt=attempt,
                total_attempts=self._max_attempts,
                error_message=f"HTTP error: {exc}",
                elapsed_ms=round(elapsed_ms, 1),
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.opt(exception=True).error(
                "Unexpected webhook error (id={}, url={!r}): {}",
                config.webhook_id,
                url,
                exc,
            )
            return WebhookResult(
                webhook_id=config.webhook_id,
                url=url,
                status_code=0,
                success=False,
                attempt=attempt,
                total_attempts=self._max_attempts,
                error_message=f"Unexpected error: {exc}",
                elapsed_ms=round(elapsed_ms, 1),
            )

    # ------------------------------------------------------------------
    # Multipart upload
    # ------------------------------------------------------------------

    def _send_multipart(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        headers: Dict[str, str],
        config: WebhookConfig,
        payload: WebhookPayload,
    ) -> httpx.Response:
        """Send a multipart/form-data request with attached files."""
        json_data = payload.to_json_dict()
        files: Dict[str, Tuple[str, Any, str]] = {}

        if config.send_image and payload.has_image:
            # Encode the numpy BGR image as JPEG bytes
            import cv2

            success, jpeg_bytes = cv2.imencode(".jpg", payload.snapshot_image)
            if success:
                files["image"] = (
                    "snapshot.jpg",
                    jpeg_bytes.tobytes(),
                    "image/jpeg",
                )

        if config.send_video and payload.has_video:
            files["video"] = (
                "clip.mp4",
                payload.video_bytes,
                "video/mp4",
            )

        # Remove content-type so httpx sets the multipart boundary
        headers.pop("content-type", None)

        return client.request(
            method,
            url,
            headers=headers,
            data={"payload": json.dumps(json_data)},
            files=files,
            timeout=self._base_timeout,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _build_auth_headers(self, config: WebhookConfig) -> Dict[str, str]:
        """Build HTTP ``Authorization`` headers based on the config.

        Args:
            config: Webhook configuration with auth settings.

        Returns:
            A dict of header name-value pairs.

        """
        auth_type = config.auth_type.lower().strip()

        if auth_type == "none" or not auth_type:
            return {}

        if auth_type == "basic":
            if not config.auth_value:
                logger.warning(
                    "Basic auth selected but auth_value is empty "
                    "(webhook_id={})",
                    config.webhook_id,
                )
                return {}
            encoded = base64.b64encode(
                config.auth_value.encode("utf-8"),
            ).decode("ascii")
            return {"authorization": f"Basic {encoded}"}

        if auth_type == "bearer":
            if not config.auth_value:
                logger.warning(
                    "Bearer auth selected but auth_value is empty "
                    "(webhook_id={})",
                    config.webhook_id,
                )
                return {}
            return {"authorization": f"Bearer {config.auth_value}"}

        if auth_type == "api_key":
            if not config.auth_value:
                logger.warning(
                    "API key auth selected but auth_value is empty "
                    "(webhook_id={})",
                    config.webhook_id,
                )
                return {}
            # Default header name is X-API-Key; user can override via
            # custom headers if needed.
            return {"x-api-key": config.auth_value}

        logger.warning(
            "Unknown auth type {!r} (webhook_id={}); treating as none",
            config.auth_type,
            config.webhook_id,
        )
        return {}

    # ------------------------------------------------------------------
    # Retry helpers
    # ------------------------------------------------------------------

    def _should_retry(self, result: WebhookResult, attempt: int) -> bool:
        """Determine whether another delivery attempt should be made.

        Args:
            result: The result of the last attempt.
            attempt: Which attempt just completed (1-indexed).

        Returns:
            ``True`` if a retry is warranted.

        """
        if attempt >= self._max_attempts:
            return False

        # Network-level errors (status_code == 0) are always retryable
        if result.status_code == 0 and result.error_message:
            return True

        # Retryable HTTP status codes
        if result.status_code in self.RETRYABLE_STATUSES:
            return True

        return False

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.Client:
        """Return the configured HTTP client.

        Creates a default ``httpx.Client`` if none was provided.

        Returns:
            An ``httpx.Client`` instance.

        """
        if self._client is not None:
            return self._client
        return httpx.Client()

    # ------------------------------------------------------------------
    # Test seam
    # ------------------------------------------------------------------

    @staticmethod
    def _sleep(delay: float) -> None:
        """Sleep for the given duration (overridable in tests).

        Args:
            delay: Seconds to sleep.

        """
        import time as time_module
        time_module.sleep(delay)

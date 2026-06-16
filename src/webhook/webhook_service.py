"""Webhook orchestration service.

Loads webhook configurations from the database, builds payloads from
detection events, dispatches via the HTTP client, and records delivery
status back on the detection record.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Set

import numpy as np
from loguru import logger

from src.detection.detection_result import DetectionResult
from src.domain.events.plate_detected import PlateDetected
from src.repositories.detection_repository import DetectionRepository
from src.repositories.webhook_repository import WebhookRepository
from src.webhook.webhook_client import WebhookClient, WebhookConfig, WebhookError
from src.webhook.webhook_payload import WebhookPayload, WebhookResult


class WebhookService:
    """Orchestrates webhook delivery for plate detection events.

    Typical flow::

        service = WebhookService(
            webhook_repo=webhook_repo,
            detection_repo=detection_repo,
            client=WebhookClient(),
        )

        # From within the detection callback
        payload = service.build_payload(event, detection_result, ocr_text="ABC123")
        results = service.deliver(camera_id=1, payload=payload)
    """

    def __init__(
        self,
        webhook_repository: WebhookRepository,
        detection_repository: DetectionRepository,
        client: Optional[WebhookClient] = None,
    ) -> None:
        """Initialise the webhook service.

        Args:
            webhook_repository: For loading webhook configs.
            detection_repository: For updating delivery status.
            client: An optional ``WebhookClient`` (created fresh if
                not provided).

        """
        self._webhook_repo = webhook_repository
        self._detection_repo = detection_repository
        self._client = client or WebhookClient()

    # ------------------------------------------------------------------
    # Build payloads
    # ------------------------------------------------------------------

    def build_payload(
        self,
        event: PlateDetected,
        detection_result: Optional[DetectionResult] = None,
        ocr_text: str = "",
        ocr_confidence: float = 0.0,
        snapshot_image: Optional[np.ndarray] = None,
        video_bytes: Optional[bytes] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> WebhookPayload:
        """Build a ``WebhookPayload`` from detection data.

        Args:
            event: The ``PlateDetected`` domain event.
            detection_result: Optional ``DetectionResult`` for
                additional bounding-box info.
            ocr_text: Recognised plate text (if OCR was applied).
            ocr_confidence: OCR confidence score.
            snapshot_image: Optional BGR frame snapshot.
            video_bytes: Optional video clip bytes.
            metadata: Additional key-value pairs to include in the
                JSON body.

        Returns:
            A populated ``WebhookPayload``.

        """
        merged_meta: Dict[str, object] = dict(metadata or {})

        if detection_result is not None:
            merged_meta.update({
                "bbox_x1": detection_result.x1,
                "bbox_y1": detection_result.y1,
                "bbox_x2": detection_result.x2,
                "bbox_y2": detection_result.y2,
                "bbox_width": detection_result.width,
                "bbox_height": detection_result.height,
            })

        return WebhookPayload(
            event_type="plate_detected",
            camera_id=event.camera_id,
            plate_text=ocr_text,
            detection_confidence=event.confidence,
            ocr_confidence=ocr_confidence,
            timestamp=event.timestamp,
            snapshot_image=snapshot_image,
            video_bytes=video_bytes,
            metadata=merged_meta,
        )

    # ------------------------------------------------------------------
    # Deliver to all webhooks for a camera
    # ------------------------------------------------------------------

    def deliver(
        self,
        camera_id: int,
        payload: WebhookPayload,
        detection_id: Optional[int] = None,
    ) -> List[WebhookResult]:
        """Deliver a payload to all active webhooks for a camera.

        Loads all webhook configurations for the given camera,
        delivers the payload to each one (with retry), and optionally
        updates the detection record's webhook status.

        Args:
            camera_id: The source camera ID.
            payload: The payload to deliver.
            detection_id: Optional detection record ID to update with
                delivery status.

        Returns:
            A list of ``WebhookResult`` objects, one per webhook
            configuration found for this camera.  An empty list means
            no webhooks are configured for the camera.

        """
        webhooks = self._webhook_repo.get_by_camera_id(camera_id)
        if not webhooks:
            logger.debug(
                "No webhooks configured for camera_id={}; skipping delivery",
                camera_id,
            )
            return []

        logger.info(
            "Delivering webhook payload for camera_id={} to {} target(s)",
            camera_id,
            len(webhooks),
        )

        results: List[WebhookResult] = []
        all_succeeded = True

        for wh in webhooks:
            config = self._model_to_config(wh, payload)
            result = self._client.send(config, payload)
            results.append(result)

            if not result.success:
                all_succeeded = False
                logger.warning(
                    "Webhook delivery failed (id={}, url={!r}, status={}): {}",
                    wh.id,
                    wh.url,
                    result.status_code,
                    result.error_message,
                )
            else:
                logger.info(
                    "Webhook delivered successfully (id={}, url={!r}, status={})",
                    wh.id,
                    wh.url,
                    result.status_code,
                )

        # Update detection status if we have a detection_id
        if detection_id is not None:
            self._update_detection_status(
                detection_id=detection_id,
                has_webhooks=True,
                all_succeeded=all_succeeded,
            )

        return results

    # ------------------------------------------------------------------
    # Deliver a payload to multiple cameras
    # ------------------------------------------------------------------

    def deliver_batch(
        self,
        camera_ids: Set[int],
        payload: WebhookPayload,
        detection_id: Optional[int] = None,
    ) -> Dict[int, List[WebhookResult]]:
        """Deliver a payload to all webhooks for multiple cameras.

        Args:
            camera_ids: A set of camera IDs.
            payload: The payload to deliver.
            detection_id: Optional detection record ID.

        Returns:
            A dict mapping each ``camera_id`` to its list of
            ``WebhookResult`` objects.

        """
        results: Dict[int, List[WebhookResult]] = {}
        for cid in camera_ids:
            camera_results = self.deliver(
                camera_id=cid,
                payload=payload,
                detection_id=detection_id,
            )
            if camera_results:
                results[cid] = camera_results
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _model_to_config(
        self,
        webhook_model: Any,
        payload: WebhookPayload,
    ) -> WebhookConfig:
        """Convert a ``WebhookModel`` ORM instance to a ``WebhookConfig``.

        Args:
            webhook_model: The ORM model instance.
            payload: The payload (used to decide whether to include
                attachments).

        Returns:
            A ``WebhookConfig`` dataclass.

        """
        headers: Dict[str, str] = {}
        if webhook_model.headers_json:
            try:
                parsed = json.loads(webhook_model.headers_json)
                if isinstance(parsed, dict):
                    headers = {str(k): str(v) for k, v in parsed.items()}
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "Invalid headers_json for webhook id={}: {}",
                    webhook_model.id,
                    exc,
                )

        return WebhookConfig(
            webhook_id=webhook_model.id,
            method=webhook_model.method,
            url=webhook_model.url,
            headers=headers,
            auth_type=webhook_model.auth_type or "none",
            auth_value=webhook_model.auth_value or "",
            body_template=webhook_model.body_template or "",
            send_image=bool(webhook_model.send_image),
            send_video=bool(webhook_model.send_video),
        )

    def _update_detection_status(
        self,
        detection_id: int,
        has_webhooks: bool,
        all_succeeded: bool,
    ) -> None:
        """Update the webhook delivery status on a detection record.

        Args:
            detection_id: The detection record's primary key.
            has_webhooks: Whether any webhooks exist for the camera.
            all_succeeded: Whether all deliveries succeeded.

        """
        if not has_webhooks:
            status = "not_configured"
        elif all_succeeded:
            status = "success"
        else:
            status = "failed"

        self._detection_repo.update_webhook_status(
            detection_id=detection_id,
            status=status,
        )
        logger.debug(
            "Updated detection {} webhook_status to {!r}",
            detection_id,
            status,
        )

    def __repr__(self) -> str:
        return "<WebhookService>"

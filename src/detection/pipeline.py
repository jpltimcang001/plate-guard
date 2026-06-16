"""Detection pipeline — orchestrates the full frame→detection→logging flow.

Pipeline stages
---------------
1. Dequeue a ``Frame`` from the camera's ``FrameCapture``.
2. Run YOLO inference via ``PlateDetectionService.detect_frame()``.
3. Filter detections through ``ZoneValidator`` (only inside zones).
4. Assign stable track IDs via ``DetectionTracker``.
5. For *new* tracks (not seen before), crop the plate region.
6. Run OCR on the cropped plate via ``PlateOcrService``.
7. Suppress duplicates via ``DuplicateFilter``.
8. Persist the detection via ``DetectionRepository``.
9. Save evidence (snapshot + video) via ``MediaWriter``.
10. Deliver webhook via ``WebhookService``.

Usage
-----
The pipeline is designed to run in a dedicated thread per camera.
It pulls frames from the camera's ``FrameCapture.queue`` in a loop::

    pipeline = DetectionPipeline(
        plate_detection_service=detection_svc,
        ocr_service=ocr_svc,
        zone_validator=zone_val,
        tracker=tracker,
        duplicate_filter=dup_filter,
        detection_repo=det_repo,
        media_writer=media_writer,
        webhook_service=webhook_svc,
    )

    while running:
        frame = capture.queue.get(timeout=1.0)
        if frame is not None:
            pipeline.process_frame(frame)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, List, Optional

import numpy as np
from loguru import logger

from src.detection.detection_result import DetectionResult
from src.detection.duplicate_filter import DuplicateFilter
from src.detection.frame_queue import Frame
from src.detection.tracker import DetectionTracker
from src.detection.zone_validator import ZoneValidator

if TYPE_CHECKING:
    from src.detection.plate_detector import PlateDetectionService
    from src.ocr.ocr_service import PlateOcrService
    from src.recorder.media_writer import MediaWriter
    from src.repositories.detection_repository import DetectionRepository
    from src.webhook.webhook_service import WebhookService


@dataclass
class PipelineResult:
    """Outcome of processing a single frame through the pipeline.

    Attributes:
        frame_number: The frame number that was processed.
        camera_id: Source camera ID.
        detections_found: Raw detections from YOLO.
        detections_in_zones: Detections that passed zone validation.
        new_tracks: Detections that started a new track.
        ocr_processed: Detections that were sent to OCR.
        ocr_successful: Detections where OCR returned non-empty text.
        duplicates_suppressed: Detections suppressed by the duplicate filter.
        detections_persisted: Detections that were saved to the database.
        processing_time_ms: Total wall-clock time for the pipeline run.
    """

    frame_number: int = 0
    camera_id: int = 0
    detections_found: int = 0
    detections_in_zones: int = 0
    new_tracks: int = 0
    ocr_processed: int = 0
    ocr_successful: int = 0
    duplicates_suppressed: int = 0
    detections_persisted: int = 0
    processing_time_ms: float = 0.0


@dataclass
class DetectionEvent:
    """A fully resolved detection ready for persistence and webhook.

    This is produced by the pipeline after zone check, tracking, OCR,
    and duplicate filtering have all passed.

    Attributes:
        camera_id: Source camera ID.
        track_id: Tracker-assigned stable track ID.
        plate_text: OCR-recognised plate text (empty if OCR failed).
        confidence: OCR confidence score.
        bounding_box: Bounding box ``(x1, y1, x2, y2)`` in pixels.
        frame: The original frame (for evidence capture).
        cropped_plate: The cropped plate sub-image.
        detected_at: Timestamp of the detection event.
        snapshot_path: Filesystem path to the saved snapshot (populated later).
        video_path: Filesystem path to the saved video clip (populated later).
    """

    camera_id: int
    track_id: int
    plate_text: str
    confidence: float
    bounding_box: tuple[int, int, int, int]
    frame: np.ndarray
    cropped_plate: np.ndarray
    detected_at: datetime = field(default_factory=datetime.now)
    snapshot_path: str | None = None
    video_path: str | None = None


class DetectionPipeline:
    """Orchestrates the full frame→detection→persistence pipeline.

    The pipeline is stateless except for the injected services.
    Per-camera state (tracker, zone cache) is managed by those
    services.

    Usage::

        pipeline = DetectionPipeline(
            plate_detection_service=...,
            ocr_service=...,
            zone_validator=...,
            tracker=...,
            duplicate_filter=...,
            detection_repo=...,
            media_writer=...,
            webhook_service=...,
        )
        result = pipeline.process_frame(frame)
    """

    def __init__(
        self,
        plate_detection_service: PlateDetectionService,
        ocr_service: PlateOcrService | None = None,
        zone_validator: ZoneValidator | None = None,
        tracker: DetectionTracker | None = None,
        duplicate_filter: DuplicateFilter | None = None,
        detection_repo: DetectionRepository | None = None,
        media_writer: MediaWriter | None = None,
        webhook_service: WebhookService | None = None,
        on_detection: Callable[[DetectionEvent], None] | None = None,
    ) -> None:
        """Initialise the detection pipeline.

        Args:
            plate_detection_service: YOLO detection service (required).
            ocr_service: OCR service for plate text recognition.
            zone_validator: Zone validator (skip zone check if ``None``).
            tracker: Detection tracker (skip tracking if ``None``).
            duplicate_filter: Duplicate filter (skip dedup if ``None``).
            detection_repo: Repository for persisting detections.
            media_writer: Media writer for snapshots/video clips.
            webhook_service: Webhook delivery service.
            on_detection: Optional callback for every successful detection
                event (after OCR, before persistence).

        """
        self._detection_service = plate_detection_service
        self._ocr_service = ocr_service
        self._zone_validator = zone_validator
        self._tracker = tracker
        self._duplicate_filter = duplicate_filter
        self._detection_repo = detection_repo
        self._media_writer = media_writer
        self._webhook_service = webhook_service
        self._on_detection = on_detection

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def detection_service(self) -> PlateDetectionService:
        """The underlying YOLO detection service."""
        return self._detection_service

    @property
    def ocr_service(self) -> Any:
        """The OCR service (may be ``None``)."""
        return self._ocr_service

    @property
    def zone_validator(self) -> Any:
        """The zone validator (may be ``None``)."""
        return self._zone_validator

    @property
    def tracker(self) -> Any:
        """The detection tracker (may be ``None``)."""
        return self._tracker

    @property
    def duplicate_filter(self) -> Any:
        """The duplicate filter (may be ``None``)."""
        return self._duplicate_filter

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def process_frame(self, frame: Frame) -> PipelineResult:
        """Run the full detection pipeline on a single frame.

        Args:
            frame: A ``Frame`` from a camera capture queue.

        Returns:
            A ``PipelineResult`` summarising what happened.

        """
        start = time.perf_counter()
        result = PipelineResult(
            frame_number=frame.frame_number,
            camera_id=frame.camera_id,
        )

        # --------------------------------------------------------------
        # Stage 1: YOLO detection
        # --------------------------------------------------------------
        if not self._detection_service.is_started:
            logger.warning(
                "Pipeline(camera={}) detection service not started",
                frame.camera_id,
            )
            return result

        detections: List[DetectionResult] = self._detection_service.detect_frame(frame)
        result.detections_found = len(detections)

        if not detections:
            result.processing_time_ms = (time.perf_counter() - start) * 1000.0
            return result

        # --------------------------------------------------------------
        # Stage 2: Zone validation
        # --------------------------------------------------------------
        if self._zone_validator is not None:
            in_zone: List[DetectionResult] = []
            for det in detections:
                if self._zone_validator.is_in_any_zone(frame.camera_id, det):
                    in_zone.append(det)
            detections = in_zone
            result.detections_in_zones = len(detections)

            if not detections:
                result.processing_time_ms = (time.perf_counter() - start) * 1000.0
                return result

        # --------------------------------------------------------------
        # Stage 3: Tracking
        # --------------------------------------------------------------
        if self._tracker is not None:
            detections = self._tracker.update(frame.camera_id, detections)

        # Count new tracks
        new_track_dets = [d for d in detections if getattr(d, "is_new", False)]
        result.new_tracks = len(new_track_dets)

        # Only process new tracks further (avoid duplicate OCR on same plate)
        if not new_track_dets:
            result.processing_time_ms = (time.perf_counter() - start) * 1000.0
            return result

        # --------------------------------------------------------------
        # Stage 4: OCR
        # --------------------------------------------------------------
        for det in new_track_dets:
            result.ocr_processed += 1

            if self._ocr_service is None or not self._ocr_service.is_started:
                # No OCR available — create a minimal DetectionEvent
                cropped = det.crop_frame(frame.data) if frame.data.size > 0 else np.array([], dtype=np.uint8)
                event = DetectionEvent(
                    camera_id=frame.camera_id,
                    track_id=getattr(det, "track_id", 0),
                    plate_text="",
                    confidence=det.confidence,
                    bounding_box=det.bounding_box,
                    frame=frame.data,
                    cropped_plate=cropped,
                )
                self._persist_event(event, result)
                continue

            try:
                ocr_result = self._ocr_service.ocr_detection(frame.data, det)
            except Exception:
                logger.opt(exception=True).warning(
                    "Pipeline(camera={}) OCR failed for track {}",
                    frame.camera_id,
                    getattr(det, "track_id", "?"),
                )
                continue

            result.ocr_successful += 1 if ocr_result.text else 0

            # --------------------------------------------------------------
            # Stage 5: Duplicate filter
            # --------------------------------------------------------------
            if self._duplicate_filter is not None and ocr_result.text:
                if not self._duplicate_filter.check_and_record(ocr_result.text):
                    result.duplicates_suppressed += 1
                    continue

            # Build the detection event
            cropped = det.crop_frame(frame.data) if frame.data.size > 0 else np.array([], dtype=np.uint8)
            event = DetectionEvent(
                camera_id=frame.camera_id,
                track_id=getattr(det, "track_id", 0),
                plate_text=ocr_result.text,
                confidence=ocr_result.confidence,
                bounding_box=det.bounding_box,
                frame=frame.data,
                cropped_plate=cropped,
                detected_at=datetime.fromtimestamp(frame.timestamp) if frame.timestamp else datetime.now(),
            )

            # --------------------------------------------------------------
            # Stage 6: Persist (evidence, DB, webhook)
            # --------------------------------------------------------------
            self._persist_event(event, result)

        result.processing_time_ms = (time.perf_counter() - start) * 1000.0
        return result

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _persist_event(
        self,
        event: DetectionEvent,
        result: PipelineResult,
    ) -> None:
        """Save evidence, database record, and fire webhook for one event.

        Args:
            event: The resolved detection event.
            result: The pipeline result to update.

        """
        # Fire callback first
        if self._on_detection is not None:
            try:
                self._on_detection(event)
            except Exception:
                logger.opt(exception=True).warning(
                    "Pipeline(camera={}) on_detection callback failed",
                    event.camera_id,
                )

        # Save snapshot
        if self._media_writer is not None and event.frame.size > 0:
            try:
                timestamp = event.detected_at.timestamp()
                event.snapshot_path = self._media_writer.save_snapshot(
                    frame=event.frame,
                    camera_id=event.camera_id,
                    timestamp=timestamp,
                    plate_text=event.plate_text,
                )
            except Exception:
                logger.opt(exception=True).warning(
                    "Pipeline(camera={}) snapshot save failed",
                    event.camera_id,
                )

        # Save to database
        if self._detection_repo is not None:
            try:
                self._save_to_db(event)
                result.detections_persisted += 1
            except Exception:
                logger.opt(exception=True).warning(
                    "Pipeline(camera={}) DB save failed",
                    event.camera_id,
                )

        # Fire webhook
        if self._webhook_service is not None:
            try:
                self._webhook_service.dispatch(event)
            except Exception:
                logger.opt(exception=True).warning(
                    "Pipeline(camera={}) webhook dispatch failed",
                    event.camera_id,
                )

    def _save_to_db(self, event: DetectionEvent) -> None:
        """Persist a detection event to the database.

        Uses the repository pattern to create a ``DetectionModel`` record.

        Args:
            event: The detection event to persist.

        """
        from src.database.models.detection_model import DetectionModel

        model = DetectionModel()
        model.camera_id = event.camera_id
        model.plate_number = event.plate_text if event.plate_text else None
        model.confidence = event.confidence
        model.image_path = event.snapshot_path
        model.video_path = event.video_path
        model.webhook_status = "pending" if self._webhook_service is not None else "not_configured"
        model.detected_at = event.detected_at

        self._detection_repo.add(model)  # type: ignore[union-attr]

    def __repr__(self) -> str:
        return (
            f"<DetectionPipeline ocr={self._ocr_service is not None} "
            f"zones={self._zone_validator is not None} "
            f"tracker={self._tracker is not None} "
            f"dedup={self._duplicate_filter is not None}>"
        )

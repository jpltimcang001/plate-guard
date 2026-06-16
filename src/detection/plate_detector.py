"""Plate detection service powered by YOLOv8.

Orchestrates:
- Model loading with GPU / CPU fallback
- Frame-level inference for one or more cameras
- Confidence threshold filtering (per-camera or global)
- Bounding-box annotation of frames
- Domain event emission for downstream consumers (OCR, webhooks, evidence)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

import cv2
import numpy as np
from loguru import logger

from src.detection.bbox_renderer import draw_detections
from src.detection.detection_result import DetectionResult
from src.detection.frame_queue import Frame
from src.detection.yolo_model import YoloModel
from src.domain.events.plate_detected import PlateDetected


class PlateDetectionService:
    """High-level service for YOLOv8 license plate detection.

    Manages a shared YOLOv8 model instance and provides per-camera
    configuration (confidence thresholds, enabled/disabled state).

    Usage::

        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()

        # Process a single frame
        detections = service.detect(frame)

        # Process a Frame from a capture queue
        events = service.process_frame(frame_obj)

        # Annotate frame
        annotated = service.annotate_frame(frame, detections)

        service.stop()
    """

    def __init__(
        self,
        model_path: str | Path = Path("models/plate.pt"),
        global_confidence_threshold: float = 0.5,
        prefer_gpu: bool = True,
        device: str | None = None,
        on_plate_detected: Optional[Callable[[PlateDetected], None]] = None,
    ) -> None:
        """Initialize the plate detection service.

        Args:
            model_path: Path to the YOLOv8 weights file.
            global_confidence_threshold: Default confidence threshold
                used when no per-camera override is configured.
            prefer_gpu: If ``True`` (default), attempt CUDA first
                and fall back to CPU.
            device: Explicit device string (e.g. ``"cuda:0"``,
                ``"cpu"``).  Overrides ``prefer_gpu``.
            on_plate_detected: Optional callback invoked for every
                detection that passes the confidence threshold.
                Receives a ``PlateDetected`` domain event.

        Raises:
            FileNotFoundError: If ``model_path`` does not exist.
            RuntimeError: If the YOLO model cannot be loaded.

        """
        self._model_path = Path(model_path)
        self._global_confidence_threshold = global_confidence_threshold
        self._on_plate_detected = on_plate_detected

        # Per-camera confidence overrides: camera_id -> threshold
        self._camera_thresholds: Dict[int, float] = {}

        # Set of camera IDs that have been started / are active
        self._active_cameras: Set[int] = set()

        self._model: Optional[YoloModel] = None
        self._started: bool = False

        logger.info(
            "PlateDetectionService initialised (model={}, threshold={})",
            self._model_path,
            self._global_confidence_threshold,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> Optional[YoloModel]:
        """The underlying YOLO model wrapper (``None`` until started)."""
        return self._model

    @property
    def is_started(self) -> bool:
        """Whether the service has been started."""
        return self._started

    @property
    def is_cuda(self) -> bool:
        """Whether the underlying model is running on CUDA."""
        return self._model is not None and self._model.is_cuda

    @property
    def global_confidence_threshold(self) -> float:
        """Default confidence threshold."""
        return self._global_confidence_threshold

    @global_confidence_threshold.setter
    def global_confidence_threshold(self, value: float) -> None:
        """Set a new default confidence threshold."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"Confidence threshold must be between 0.0 and 1.0, got {value}",
            )
        self._global_confidence_threshold = value
        if self._model is not None:
            self._model.confidence_threshold = value
        logger.info("Global confidence threshold set to {:.2f}", value)

    @property
    def active_camera_count(self) -> int:
        """Number of cameras currently being processed."""
        return len(self._active_cameras)

    @property
    def model_path(self) -> Path:
        """Path to the YOLO weights file."""
        return self._model_path

    # ------------------------------------------------------------------
    # Per-camera thresholds
    # ------------------------------------------------------------------

    def set_camera_threshold(self, camera_id: int, threshold: float) -> None:
        """Override the confidence threshold for a specific camera.

        Args:
            camera_id: The camera ID.
            threshold: Confidence threshold (``0.0``–``1.0``).

        Raises:
            ValueError: If the threshold is out of range.

        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"Confidence threshold must be between 0.0 and 1.0, got {threshold}",
            )
        self._camera_thresholds[camera_id] = threshold
        logger.debug(
            "Per-camera threshold set: camera={}, threshold={:.2f}",
            camera_id,
            threshold,
        )

    def get_camera_threshold(self, camera_id: int) -> float:
        """Return the effective threshold for a camera.

        Falls back to the global threshold if no per-camera override
        is configured.

        Args:
            camera_id: The camera ID.

        Returns:
            The effective confidence threshold.

        """
        return self._camera_thresholds.get(
            camera_id,
            self._global_confidence_threshold,
        )

    def remove_camera_threshold(self, camera_id: int) -> None:
        """Remove a per-camera threshold override.

        After this call the camera will use the global threshold.

        Args:
            camera_id: The camera ID.

        """
        self._camera_thresholds.pop(camera_id, None)
        logger.debug("Per-camera threshold removed: camera={}", camera_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Load the YOLO model and prepare the service for inference.

        Raises:
            RuntimeError: If already started or the model cannot load.

        """
        if self._started:
            raise RuntimeError("PlateDetectionService is already started")

        logger.info("Starting PlateDetectionService...")
        self._model = YoloModel(
            model_path=self._model_path,
            confidence_threshold=self._global_confidence_threshold,
            prefer_gpu=True,
        )
        self._started = True
        logger.info(
            "PlateDetectionService started (device={})",
            self._model.device_name,
        )

    def stop(self) -> None:
        """Shut down the service and release the model."""
        if not self._started:
            return

        logger.info("Stopping PlateDetectionService...")
        self._model = None
        self._active_cameras.clear()
        self._started = False
        logger.info("PlateDetectionService stopped")

    # ------------------------------------------------------------------
    # Single-frame detection
    # ------------------------------------------------------------------

    def detect(
        self,
        frame: np.ndarray,
        confidence_threshold: float | None = None,
    ) -> List[DetectionResult]:
        """Run plate detection on a single frame.

        Args:
            frame: BGR frame as a numpy array ``(H, W, 3)``.
            confidence_threshold: Override threshold for this call.
                ``None`` uses the global threshold.

        Returns:
            A list of ``DetectionResult``, empty if nothing found.

        Raises:
            RuntimeError: If the service has not been started.

        """
        if self._model is None:
            raise RuntimeError(
                "PlateDetectionService has not been started; call start() first",
            )

        return self._model.predict(
            frame,
            confidence_threshold=confidence_threshold,
        )

    def detect_frame(
        self,
        frame: Frame,
    ) -> List[DetectionResult]:
        """Run detection on a ``Frame`` object from a capture queue.

        Uses the per-camera confidence threshold for the frame's
        camera.

        Args:
            frame: A ``Frame`` instance with ``.data`` as the BGR image.

        Returns:
            A list of ``DetectionResult``.

        """
        threshold = self.get_camera_threshold(frame.camera_id)
        return self.detect(frame.data, confidence_threshold=threshold)

    # ------------------------------------------------------------------
    # Frame processing with event emission
    # ------------------------------------------------------------------

    def process_frame(
        self,
        frame: Frame,
    ) -> List[PlateDetected]:
        """Process a single frame: detect and emit domain events.

        This is the primary entry point for the detection pipeline.
        It runs inference, filters results, optionally fires the
        ``on_plate_detected`` callback, and returns domain events
        for downstream processing (OCR, webhooks, evidence capture).

        Args:
            frame: A ``Frame`` from a camera capture queue.

        Returns:
            A list of ``PlateDetected`` domain events (one per
            detection above the camera's threshold).

        """
        from datetime import datetime

        detections = self.detect_frame(frame)
        events: List[PlateDetected] = []

        for det in detections:
            event = PlateDetected(
                camera_id=frame.camera_id,
                bounding_box=det.bounding_box,
                confidence=det.confidence,
                timestamp=datetime.fromtimestamp(frame.timestamp),
            )
            events.append(event)

            # Fire callback
            if self._on_plate_detected is not None:
                try:
                    self._on_plate_detected(event)
                except Exception:
                    logger.opt(exception=True).warning(
                        "PlateDetectionService on_plate_detected callback failed "
                        "for camera={}",
                        frame.camera_id,
                    )

        return events

    # ------------------------------------------------------------------
    # Annotation
    # ------------------------------------------------------------------

    def annotate_frame(
        self,
        frame: np.ndarray,
        detections: List[DetectionResult],
        *,
        show_label: bool = True,
        show_confidence: bool = True,
    ) -> np.ndarray:
        """Draw detection results onto a frame.

        This is a convenience wrapper around ``draw_detections``
        that uses sensible defaults.

        Args:
            frame: Original BGR frame.
            detections: Detections to draw.
            show_label: Whether to show class labels.
            show_confidence: Whether to show confidence scores.

        Returns:
            Annotated BGR frame.

        """
        return draw_detections(
            frame=frame,
            detections=detections,
            show_label=show_label,
            show_confidence=show_confidence,
        )

    # ------------------------------------------------------------------
    # Camera activity tracking
    # ------------------------------------------------------------------

    def register_camera(self, camera_id: int) -> None:
        """Register a camera as active for detection.

        Args:
            camera_id: The camera ID.

        """
        self._active_cameras.add(camera_id)
        logger.debug("Camera registered for detection: id={}", camera_id)

    def unregister_camera(self, camera_id: int) -> None:
        """Unregister a camera (stop processing its frames).

        Args:
            camera_id: The camera ID.

        """
        self._active_cameras.discard(camera_id)
        self._camera_thresholds.pop(camera_id, None)
        logger.debug("Camera unregistered from detection: id={}", camera_id)

    # ------------------------------------------------------------------
    # Batch / multi-camera processing
    # ------------------------------------------------------------------

    def process_frames(
        self,
        frames: List[Frame],
    ) -> Dict[int, List[PlateDetected]]:
        """Process a batch of frames from multiple cameras.

        Each frame is processed independently.  Results are keyed
        by ``camera_id``.

        Args:
            frames: A list of ``Frame`` objects (may come from
                different cameras).

        Returns:
            A dict mapping ``camera_id`` to a list of ``PlateDetected``
            events for that camera.

        """
        results: Dict[int, List[PlateDetected]] = {}
        for frame in frames:
            if frame.camera_id not in self._active_cameras:
                continue
            events = self.process_frame(frame)
            if events:
                results.setdefault(frame.camera_id, []).extend(events)
        return results

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def warmup(self) -> None:
        """Run a single inference on a dummy frame to warm up the model.

        This loads CUDA kernels and reduces latency on the first
        real detection.  Safe to call after ``start()``.

        """
        if self._model is None:
            return

        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        _ = self._model.predict(dummy, confidence_threshold=1.0)
        logger.debug("YOLO model warmup complete")

    def stats(self) -> dict:
        """Return a snapshot of service statistics.

        Returns:
            A dict with keys: ``started``, ``device``, ``is_cuda``,
            ``model_path``, ``global_threshold``, ``active_cameras``,
            ``inference_count``, ``avg_inference_ms``.

        """
        return {
            "started": self._started,
            "device": self._model.device_name if self._model else None,
            "is_cuda": self.is_cuda,
            "model_path": str(self._model_path),
            "global_threshold": self._global_confidence_threshold,
            "active_cameras": len(self._active_cameras),
            "inference_count": self._model.inference_count if self._model else 0,
            "avg_inference_ms": round(self._model.avg_inference_ms, 2)
            if self._model
            else 0.0,
        }

    def __repr__(self) -> str:
        return (
            f"<PlateDetectionService started={self._started} "
            f"device={self._model.device_name if self._model else 'N/A'} "
            f"cameras={len(self._active_cameras)}>"
        )

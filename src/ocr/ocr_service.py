"""Plate OCR service powered by PaddleOCR.

Orchestrates:
- PaddleOCR engine lifecycle (lazy initialisation)
- Cropping plate regions from YOLO detections
- Text recognition with confidence scoring
- Error handling for empty crops, failed inference, and missing
  dependencies
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from src.detection.detection_result import DetectionResult
from src.ocr.ocr_result import OcrResult


class OcrError(Exception):
    """Raised when OCR inference fails for a non-trivial reason.

    Does **not** cover cases where no text is found in a valid crop
    — that is a normal outcome represented by an ``OcrResult`` with
    empty ``text``.
    """


class PlateOcrService:
    """High-level service for license-plate OCR using PaddleOCR.

    Usage::

        service = PlateOcrService(lang="en")
        service.start()

        # OCR a single detection
        result = service.ocr_detection(frame, detection)
        print(result.text, result.confidence)

        # OCR multiple detections from the same frame
        results = service.ocr_detections(frame, detections)

        service.stop()
    """

    def __init__(
        self,
        lang: str = "en",
        confidence_threshold: float = 0.5,
        use_gpu: bool = True,
        max_text_length: int = 15,
        **paddle_kwargs: Any,
    ) -> None:
        """Initialise the OCR service.

        Args:
            lang: Language code for PaddleOCR (default ``"en"``).
            confidence_threshold: Minimum OCR confidence to retain a
                result.  Results below this threshold will have their
                ``text`` set to ``""``.
            use_gpu: If ``True`` (default), attempt to use GPU
                acceleration.  Falls back to CPU if GPU is unavailable
                or loading fails.
            max_text_length: Maximum number of characters expected in a
                plate.  Useful for filtering spurious long reads.
            paddle_kwargs: Additional keyword arguments forwarded to
                the ``PaddleOCR`` constructor (e.g. ``det_db_thresh``,
                ``rec_batch_num``).

        """
        self._lang: str = lang
        self._confidence_threshold: float = confidence_threshold
        self._use_gpu: bool = use_gpu
        self._max_text_length: int = max_text_length
        self._paddle_kwargs: Dict[str, Any] = paddle_kwargs

        self._ocr: Any = None  # PaddleOCR instance (lazy)
        self._started: bool = False

        logger.info(
            "PlateOcrService initialised (lang={}, threshold={}, gpu={})",
            self._lang,
            self._confidence_threshold,
            self._use_gpu,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_started(self) -> bool:
        """Whether the OCR engine has been started."""
        return self._started

    @property
    def lang(self) -> str:
        """Language code used by the OCR engine."""
        return self._lang

    @property
    def confidence_threshold(self) -> float:
        """Minimum OCR confidence to retain recognised text."""
        return self._confidence_threshold

    @confidence_threshold.setter
    def confidence_threshold(self, value: float) -> None:
        """Set a new confidence threshold."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"Confidence threshold must be between 0.0 and 1.0, got {value}",
            )
        self._confidence_threshold = value
        logger.info("OCR confidence threshold set to {:.2f}", value)

    @property
    def use_gpu(self) -> bool:
        """Whether GPU acceleration is enabled."""
        return self._use_gpu

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise the PaddleOCR engine.

        Raises:
            RuntimeError: If already started.
            OcrError: If PaddleOCR cannot be imported or initialised.

        """
        if self._started:
            raise RuntimeError("PlateOcrService is already started")

        logger.info("Starting PlateOcrService...")

        try:
            self._ocr = self._create_engine()
        except ImportError as exc:
            raise OcrError(
                "PaddleOCR is not installed. "
                "Install it with: pip install paddleocr",
            ) from exc
        except Exception as exc:
            raise OcrError(
                f"Failed to initialise PaddleOCR engine: {exc}",
            ) from exc

        self._started = True
        logger.info("PlateOcrService started (lang={}, gpu={})", self._lang, self._use_gpu)

    def stop(self) -> None:
        """Shut down the OCR engine and release resources."""
        if not self._started:
            return

        logger.info("Stopping PlateOcrService...")
        self._ocr = None
        self._started = False
        logger.info("PlateOcrService stopped")

    # ------------------------------------------------------------------
    # Engine creation (overridable for testing)
    # ------------------------------------------------------------------

    def _create_engine(self) -> Any:
        """Create and return a PaddleOCR instance.

        This method is separate so that tests can override it without
        needing PaddleOCR installed.

        Returns:
            A ``paddleocr.PaddleOCR`` instance.

        Raises:
            ImportError: If ``paddleocr`` is not installed.

        """
        from paddleocr import PaddleOCR

        return PaddleOCR(
            lang=self._lang,
            use_gpu=self._use_gpu,
            show_log=False,
            **self._paddle_kwargs,
        )

    # ------------------------------------------------------------------
    # Core OCR
    # ------------------------------------------------------------------

    def ocr_crop(self, crop: np.ndarray) -> OcrResult:
        """Run OCR on a pre-cropped plate image.

        Args:
            crop: A BGR numpy array containing the licence plate
                sub-image.  May be empty (zero-size).

        Returns:
            An ``OcrResult`` with the recognised text and confidence.
            Returns an empty ``OcrResult`` if the crop is invalid or
            no text is found.

        Raises:
            RuntimeError: If the service has not been started.
            OcrError: If the OCR engine raises an unexpected error.

        """
        self._require_started()

        # Guard against empty / invalid crops
        if crop.size == 0 or crop.ndim != 3 or crop.shape[2] != 3:
            logger.debug("Skipping OCR on empty or invalid crop (size={})", crop.size)
            return OcrResult.empty(reason="empty or invalid crop")

        start = time.perf_counter()

        try:
            raw_results: List[Any] = self._ocr.ocr(crop, cls=False)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            logger.opt(exception=True).error(
                "PaddleOCR inference failed after {:.1f}ms: {}",
                elapsed,
                exc,
            )
            raise OcrError(f"OCR inference failed: {exc}") from exc

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return self._parse_paddle_result(raw_results, processing_time_ms=elapsed_ms)

    def ocr_detection(
        self,
        frame: np.ndarray,
        detection: DetectionResult,
    ) -> OcrResult:
        """Crop a detection from the frame and run OCR on it.

        This is a convenience method equivalent to::

            crop = detection.crop_frame(frame)
            service.ocr_crop(crop)

        Args:
            frame: The original BGR frame as a numpy array.
            detection: A ``DetectionResult`` whose bounding box
                defines the region to crop and OCR.

        Returns:
            An ``OcrResult``.

        """
        crop = detection.crop_frame(frame)
        return self.ocr_crop(crop)

    def ocr_detections(
        self,
        frame: np.ndarray,
        detections: List[DetectionResult],
    ) -> List[OcrResult]:
        """Run OCR on multiple detections from the same frame.

        Each detection is cropped and OCR'd independently.

        Args:
            frame: The original BGR frame.
            detections: A list of ``DetectionResult`` objects.

        Returns:
            A list of ``OcrResult`` instances, one per detection,
            in the same order as ``detections``.

        """
        return [self.ocr_detection(frame, det) for det in detections]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_started(self) -> None:
        """Guard method that raises if the service is not started."""
        if not self._started or self._ocr is None:
            raise RuntimeError(
                "PlateOcrService has not been started; call start() first",
            )

    def _parse_paddle_result(
        self,
        raw_results: List[Any],
        processing_time_ms: float = 0.0,
    ) -> OcrResult:
        """Convert raw PaddleOCR output to an ``OcrResult``.

        PaddleOCR returns a list where each element corresponds to a
        detected text region.  Each region is::

            [ [[x1,y1],[x2,y1],[x2,y2],[x1,y2]], (text, confidence) ]

        We take the region with the **highest** confidence as the
        plate result.

        Args:
            raw_results: The raw output from ``PaddleOCR.ocr()``.
            processing_time_ms: How long the OCR inference took.

        Returns:
            A populated ``OcrResult``, or an empty one if no text
            was found.

        """
        # PaddleOCR returns None when no text is detected
        if not raw_results:
            return OcrResult(
                text="",
                confidence=0.0,
                bounding_box=None,
                processing_time_ms=processing_time_ms,
                raw_text="",
            )

        # Find the highest-confidence text region
        best_text: str = ""
        best_conf: float = 0.0
        best_box: Optional[Tuple[int, int, int, int]] = None
        best_raw: str = ""

        for region in raw_results:
            if region is None:
                continue
            # Each region is [polygon_points, (text, confidence)]
            if not isinstance(region, (list, tuple)) or len(region) != 2:
                continue

            poly, (text, conf) = region

            if not isinstance(conf, (int, float)) or conf < 0.0:
                continue

            if conf > best_conf:
                best_conf = conf
                best_text = str(text).strip() if text else ""
                best_raw = str(text) if text else ""
                best_box = self._polygon_to_bbox(poly)

        # Apply confidence threshold
        if best_conf < self._confidence_threshold:
            return OcrResult(
                text="",
                confidence=best_conf,
                bounding_box=best_box,
                processing_time_ms=processing_time_ms,
                raw_text=best_raw,
            )

        # Apply max text length filter
        if len(best_text) > self._max_text_length:
            logger.debug(
                "OCR result exceeded max_text_length ({} > {}): {!r}",
                len(best_text),
                self._max_text_length,
                best_text,
            )
            return OcrResult(
                text="",
                confidence=best_conf,
                bounding_box=best_box,
                processing_time_ms=processing_time_ms,
                raw_text=best_raw,
            )

        return OcrResult(
            text=best_text,
            confidence=best_conf,
            bounding_box=best_box,
            processing_time_ms=processing_time_ms,
            raw_text=best_raw,
        )

    @staticmethod
    def _polygon_to_bbox(
        polygon: List[List[float]],
    ) -> Tuple[int, int, int, int]:
        """Convert a PaddleOCR polygon to an axis-aligned bounding box.

        PaddleOCR returns polygons as lists of four ``[x, y]`` points
        in clockwise order starting from top-left.

        Args:
            polygon: A list of four ``[x, y]`` coordinate pairs.

        Returns:
            An ``(x1, y1, x2, y2)`` tuple in pixel coordinates.

        """
        xs = [int(pt[0]) for pt in polygon]
        ys = [int(pt[1]) for pt in polygon]
        return (min(xs), min(ys), max(xs), max(ys))

    def __repr__(self) -> str:
        return (
            f"<PlateOcrService started={self._started} "
            f"lang={self._lang} "
            f"threshold={self._confidence_threshold:.2f} "
            f"gpu={self._use_gpu}>"
        )

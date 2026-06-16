"""YOLO model wrapper with automatic GPU / CPU fallback.

Wraps ``ultralytics.YOLO`` to provide:
- GPU (CUDA) acceleration when available
- Transparent CPU fallback when CUDA is unavailable or fails
- Configurable confidence threshold
- Thread-safe inference (each call uses a fresh tensor)
- Lightweight statistics tracking
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
from loguru import logger

from src.detection.detection_result import DetectionResult


class YoloModel:
    """Thread-safe wrapper around an ``ultralytics.YOLO`` model.

    Usage::

        model = YoloModel("models/plate.pt", confidence_threshold=0.5)
        results: list[DetectionResult] = model.predict(frame)

    The model automatically selects GPU if ``torch.cuda.is_available()``
    and falls back to CPU if CUDA is unavailable or model loading with
    CUDA fails.
    """

    def __init__(
        self,
        model_path: str | Path,
        confidence_threshold: float = 0.5,
        prefer_gpu: bool = True,
        device: str | None = None,
    ) -> None:
        """Initialize the YOLO model.

        Args:
            model_path: Path to the ``.pt`` weights file.
            confidence_threshold: Minimum confidence to retain a
                detection (``0.0``–``1.0``).
            prefer_gpu: If ``True`` (default), attempt to load the
                model on CUDA first and fall back to CPU on failure.
            device: Explicit device string (e.g. ``"cuda:0"``,
                ``"cpu"``).  Overrides ``prefer_gpu``.

        Raises:
            FileNotFoundError: If ``model_path`` does not exist.
            RuntimeError: If the model cannot be loaded on any device.

        """
        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(
                f"YOLO model not found at: {model_path.resolve()}",
            )

        self._model_path: Path = model_path
        self._confidence_threshold: float = confidence_threshold
        self._device: str | None = device
        self._model: Any = None
        self._device_name: str = "unknown"
        self._load_count: int = 0
        self._inference_count: int = 0
        self._total_inference_ms: float = 0.0

        self._load_model(prefer_gpu=prefer_gpu)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model_path(self) -> Path:
        """Path to the YOLO weights file."""
        return self._model_path

    @property
    def confidence_threshold(self) -> float:
        """Minimum confidence threshold for detections."""
        return self._confidence_threshold

    @confidence_threshold.setter
    def confidence_threshold(self, value: float) -> None:
        """Set a new confidence threshold."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"Confidence threshold must be between 0.0 and 1.0, got {value}",
            )
        self._confidence_threshold = value

    @property
    def device_name(self) -> str:
        """Current device the model is running on (``"cuda"`` or ``"cpu"``)."""
        return self._device_name

    @property
    def is_cuda(self) -> bool:
        """Whether the model is running on a CUDA device."""
        return self._device_name.startswith("cuda")

    @property
    def load_count(self) -> int:
        """Number of times the model weights have been loaded."""
        return self._load_count

    @property
    def inference_count(self) -> int:
        """Total number of inference calls made."""
        return self._inference_count

    @property
    def total_inference_ms(self) -> float:
        """Cumulative inference time in milliseconds."""
        return self._total_inference_ms

    @property
    def avg_inference_ms(self) -> float:
        """Average inference time per call in milliseconds."""
        if self._inference_count == 0:
            return 0.0
        return self._total_inference_ms / self._inference_count

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(
        self,
        frame: np.ndarray,
        confidence_threshold: float | None = None,
    ) -> List[DetectionResult]:
        """Run YOLO inference on a single frame.

        Args:
            frame: BGR image as a numpy array ``(H, W, 3)``.
            confidence_threshold: Override the instance threshold for
                this call.  ``None`` uses the instance default.

        Returns:
            A list of ``DetectionResult`` objects, ordered by
            descending confidence.  An empty list means no detections
            above the threshold.

        """
        import time

        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self._confidence_threshold
        )

        start = time.perf_counter()
        results = self._model.predict(
            source=frame,
            conf=threshold,
            verbose=False,
            device=self._device_name,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self._inference_count += 1
        self._total_inference_ms += elapsed_ms

        detections: List[DetectionResult] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                # xyxyn is normalized — convert to pixel coordinates
                x1_n, y1_n, x2_n, y2_n = box.xyxyn[0].tolist()
                h, w = frame.shape[:2]
                x1_px = int(x1_n * w)
                y1_px = int(y1_n * h)
                x2_px = int(x2_n * w)
                y2_px = int(y2_n * h)

                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                class_name = (
                    result.names[class_id]
                    if result.names and class_id in result.names
                    else str(class_id)
                )

                detections.append(
                    DetectionResult(
                        bounding_box=(x1_px, y1_px, x2_px, y2_px),
                        confidence=confidence,
                        class_id=class_id,
                        class_name=class_name,
                    ),
                )

        # Sort by confidence descending
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self, prefer_gpu: bool = True) -> None:
        """Load the YOLO model, attempting GPU first if requested.

        Args:
            prefer_gpu: If ``True``, try CUDA first.

        Raises:
            RuntimeError: If the model cannot be loaded.

        """
        import torch

        if self._device is not None:
            # Explicit device was provided — use it
            self._load_on_device(self._device)
            return

        if prefer_gpu and torch.cuda.is_available():
            try:
                self._load_on_device("cuda:0")
                logger.info(
                    "YOLO model loaded on CUDA: {}",
                    self._model_path,
                )
                return
            except Exception as exc:
                logger.warning(
                    "Failed to load YOLO model on CUDA, falling back to CPU: {}",
                    exc,
                )

        self._load_on_device("cpu")
        logger.info("YOLO model loaded on CPU: {}", self._model_path)

    def _load_on_device(self, device: str) -> None:
        """Load the model on a specific device.

        Args:
            device: Device string (``"cuda:0"``, ``"cpu"``, etc.).

        Raises:
            RuntimeError: If loading fails.

        """
        from ultralytics import YOLO

        try:
            self._model = YOLO(str(self._model_path))
            self._model.to(device)
            self._device_name = device
            self._load_count += 1
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load YOLO model on device '{device}': {exc}",
            ) from exc

    def __repr__(self) -> str:
        return (
            f"<YoloModel device={self._device_name} "
            f"model={self._model_path.name} "
            f"threshold={self._confidence_threshold:.2f} "
            f"inferences={self._inference_count}>"
        )

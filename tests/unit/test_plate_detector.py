"""Unit tests for YoloModel, PlateDetectionService, and bbox_renderer.

Uses mocking for the YOLO model so no GPU or weights file is required.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest

from src.detection.bbox_renderer import (
    crop_detections,
    draw_detection_centers,
    draw_detections,
)
from src.detection.detection_result import DetectionResult
from src.detection.frame_queue import Frame
from src.detection.plate_detector import PlateDetectionService
from src.detection.yolo_model import YoloModel

# ======================================================================
# Fake / mock helpers
# ======================================================================


def _make_dummy_frame(camera_id: int = 1) -> Frame:
    """Return a Frame with a small synthetic image."""
    return Frame(
        data=np.zeros((48, 64, 3), dtype=np.uint8),
        camera_id=camera_id,
        timestamp=time.time(),
        frame_number=42,
    )


def _make_fake_yolo_result(
    boxes_xyxyn: List[List[float]],
    confs: List[float],
    cls_ids: List[int],
    class_names: dict,
) -> MagicMock:
    """Build a mock ultralytics Results object."""
    mock_result = MagicMock()
    mock_result.names = class_names

    mock_boxes = MagicMock()
    mock_boxes_list: List[MagicMock] = []
    for xy, conf, cid in zip(boxes_xyxyn, confs, cls_ids):
        box = MagicMock()
        # Use a numpy array so that [0].tolist() works in predict()
        box.xyxyn = np.array([xy])
        box.conf = [conf]
        box.cls = [cid]
        mock_boxes_list.append(box)
    mock_boxes.__iter__.return_value = mock_boxes_list
    mock_result.boxes = mock_boxes
    return mock_result


# ======================================================================
# YoloModel
# ======================================================================


class TestYoloModelInit:
    """Tests for YoloModel initialisation and model loading."""

    def test_init_raises_file_not_found(self) -> None:
        """YoloModel raises FileNotFoundError for a non-existent path."""
        with pytest.raises(FileNotFoundError, match="YOLO model not found"):
            YoloModel(model_path="nonexistent/path.pt")

    @patch("ultralytics.YOLO")
    def test_init_success_with_valid_path(
        self,
        mock_yolo_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """YoloModel initialises with a valid path and default threshold."""
        model_path = tmp_path / "plate.pt"
        model_path.touch()
        mock_yolo_class.return_value = MagicMock()
        model = YoloModel(model_path=model_path)
        assert model.confidence_threshold == 0.5
        assert model.model_path == model_path

    @patch("ultralytics.YOLO")
    def test_confidence_threshold_setter(
        self,
        mock_yolo_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting confidence threshold updates the value."""
        model_path = tmp_path / "plate.pt"
        model_path.touch()
        mock_yolo_class.return_value = MagicMock()
        model = YoloModel(model_path=model_path)
        model.confidence_threshold = 0.75
        assert model.confidence_threshold == 0.75

    @patch("ultralytics.YOLO")
    def test_confidence_threshold_setter_invalid(
        self,
        mock_yolo_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting an out-of-range threshold raises ValueError."""
        model_path = tmp_path / "plate.pt"
        model_path.touch()
        mock_yolo_class.return_value = MagicMock()
        model = YoloModel(model_path=model_path)
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            model.confidence_threshold = 1.5
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            model.confidence_threshold = -0.1


class TestYoloModelDeviceFallback:
    """Tests for GPU / CPU fallback logic."""

    @patch("ultralytics.YOLO")
    @patch("torch.cuda.is_available", return_value=False)
    def test_cpu_fallback_when_cuda_unavailable(
        self,
        mock_cuda: MagicMock,
        mock_yolo_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When CUDA is unavailable, model loads on CPU."""
        model_path = tmp_path / "test.pt"
        model_path.touch()

        mock_instance = MagicMock()
        mock_yolo_class.return_value = mock_instance

        model = YoloModel(model_path=model_path, prefer_gpu=True)
        assert model.device_name == "cpu"
        assert not model.is_cuda

    @patch("ultralytics.YOLO")
    @patch("torch.cuda.is_available", return_value=True)
    def test_cuda_used_when_available(
        self,
        mock_cuda: MagicMock,
        mock_yolo_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When CUDA is available, model loads on CUDA."""
        model_path = tmp_path / "test.pt"
        model_path.touch()

        mock_instance = MagicMock()
        mock_yolo_class.return_value = mock_instance

        model = YoloModel(model_path=model_path, prefer_gpu=True)
        assert model.device_name == "cuda:0"
        assert model.is_cuda

    @patch("ultralytics.YOLO")
    @patch("torch.cuda.is_available", return_value=True)
    def test_fallback_to_cpu_when_cuda_fails(
        self,
        mock_cuda: MagicMock,
        mock_yolo_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When CUDA loading fails, falls back to CPU."""
        model_path = tmp_path / "test.pt"
        model_path.touch()

        mock_instance = MagicMock()
        mock_yolo_class.return_value = mock_instance

        def _to_side_effect(device: str) -> None:
            if device == "cuda:0":
                raise RuntimeError("CUDA OOM")

        mock_instance.to.side_effect = _to_side_effect

        model = YoloModel(model_path=model_path, prefer_gpu=True)
        assert model.device_name == "cpu"
        assert not model.is_cuda
        assert model.load_count == 1  # only CPU load counted


class TestYoloModelPredict:
    """Tests for YOLO inference (with mocked ultralytics)."""

    def _make_model(self, tmp_path: Path) -> YoloModel:
        """Create a YoloModel with a mocked _model for testing."""
        model_path = tmp_path / "plate.pt"
        model_path.touch()
        with patch("ultralytics.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            model = YoloModel(model_path=model_path)
        model._model = MagicMock()  # Replace the real model with a mock
        return model

    def test_predict_returns_empty_when_no_detections(self, tmp_path: Path) -> None:
        """predict returns empty list when model finds nothing."""
        model = self._make_model(tmp_path)
        empty_result = MagicMock()
        empty_result.boxes = None
        model._model.predict.return_value = [empty_result]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = model.predict(frame)
        assert detections == []

    def test_predict_returns_detections(self, tmp_path: Path) -> None:
        """predict returns detection results with correct attributes."""
        model = self._make_model(tmp_path)

        fake_result = _make_fake_yolo_result(
            boxes_xyxyn=[[0.1, 0.2, 0.5, 0.6]],
            confs=[0.85],
            cls_ids=[0],
            class_names={0: "plate"},
        )
        model._model.predict.return_value = [fake_result]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = model.predict(frame)

        assert len(detections) == 1
        det = detections[0]
        # xyxyn * frame dims: 0.1*640=64, 0.2*480=96, 0.5*640=320, 0.6*480=288
        assert det.bounding_box == (64, 96, 320, 288)
        assert det.confidence == pytest.approx(0.85)
        assert det.class_id == 0
        assert det.class_name == "plate"

    def test_predict_sorts_by_confidence_descending(self, tmp_path: Path) -> None:
        """predict returns detections ordered by confidence descending."""
        model = self._make_model(tmp_path)

        fake_result = _make_fake_yolo_result(
            boxes_xyxyn=[
                [0.1, 0.1, 0.3, 0.3],
                [0.4, 0.4, 0.6, 0.6],
                [0.7, 0.7, 0.9, 0.9],
            ],
            confs=[0.5, 0.9, 0.7],
            cls_ids=[0, 0, 0],
            class_names={0: "plate"},
        )
        model._model.predict.return_value = [fake_result]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = model.predict(frame)

        assert len(detections) == 3
        assert detections[0].confidence == pytest.approx(0.9)
        assert detections[1].confidence == pytest.approx(0.7)
        assert detections[2].confidence == pytest.approx(0.5)

    def test_predict_with_custom_threshold(self, tmp_path: Path) -> None:
        """predict passes custom threshold to the model."""
        model = self._make_model(tmp_path)

        model._model.predict.return_value = [
            _make_fake_yolo_result(
                boxes_xyxyn=[[0.1, 0.1, 0.3, 0.3]],
                confs=[0.95],
                cls_ids=[0],
                class_names={0: "plate"},
            ),
        ]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = model.predict(frame, confidence_threshold=0.9)
        assert len(detections) == 1

        # Verify the conf argument was passed
        _call_kwargs = model._model.predict.call_args[1]
        assert _call_kwargs["conf"] == 0.9

    def test_predict_uses_instance_threshold_when_none(self, tmp_path: Path) -> None:
        """When confidence_threshold is None, the instance threshold is used."""
        model = self._make_model(tmp_path)
        model.confidence_threshold = 0.42

        model._model.predict.return_value = [
            _make_fake_yolo_result(
                boxes_xyxyn=[[0.1, 0.1, 0.3, 0.3]],
                confs=[0.95],
                cls_ids=[0],
                class_names={0: "plate"},
            ),
        ]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        model.predict(frame, confidence_threshold=None)
        _call_kwargs = model._model.predict.call_args[1]
        assert _call_kwargs["conf"] == 0.42


class TestYoloModelStats:
    """Tests for YoloModel statistics tracking."""

    def _make_model(self, tmp_path: Path) -> YoloModel:
        model_path = tmp_path / "plate.pt"
        model_path.touch()
        with patch("ultralytics.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            model = YoloModel(model_path=model_path)
        model._model = MagicMock()
        return model

    def test_inference_count_tracked(self, tmp_path: Path) -> None:
        """Each predict call increments the inference counter."""
        model = self._make_model(tmp_path)
        model._model.predict.return_value = [
            _make_fake_yolo_result(
                boxes_xyxyn=[[0.1, 0.1, 0.3, 0.3]],
                confs=[0.9],
                cls_ids=[0],
                class_names={0: "plate"},
            ),
        ]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        assert model.inference_count == 0
        model.predict(frame)
        assert model.inference_count == 1
        model.predict(frame)
        assert model.inference_count == 2

    def test_total_inference_ms_increases(self, tmp_path: Path) -> None:
        """Each predict call adds to cumulative inference time."""
        model = self._make_model(tmp_path)
        model._model.predict.return_value = [
            _make_fake_yolo_result(
                boxes_xyxyn=[[0.1, 0.1, 0.3, 0.3]],
                confs=[0.9],
                cls_ids=[0],
                class_names={0: "plate"},
            ),
        ]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        assert model.total_inference_ms == 0.0
        model.predict(frame)
        assert model.total_inference_ms > 0.0
        model.predict(frame)
        assert model.total_inference_ms > 0.0
        assert model.inference_count == 2
        assert model.avg_inference_ms > 0.0


# ======================================================================
# PlateDetectionService
# ======================================================================


class TestPlateDetectionServiceLifecycle:
    """Tests for service start / stop."""

    def test_init_defaults(self) -> None:
        """Service initialises with default values and is not started."""
        service = PlateDetectionService(model_path="models/plate.pt")
        assert not service.is_started
        assert service.model is None
        assert service.global_confidence_threshold == 0.5
        assert service.active_camera_count == 0
        # Check path uses forward slashes or os-agnostic
        path_str = str(service.model_path).replace(os.sep, "/")
        assert path_str.endswith("models/plate.pt")

    @patch("src.detection.plate_detector.YoloModel")
    def test_start_loads_model(self, mock_yolo_class: MagicMock) -> None:
        """start() loads the YOLO model and sets is_started."""
        mock_instance = MagicMock()
        mock_yolo_class.return_value = mock_instance

        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()

        assert service.is_started
        assert service.model is not None
        mock_yolo_class.assert_called_once_with(
            model_path=service.model_path,
            confidence_threshold=0.5,
            prefer_gpu=True,
        )

    @patch("src.detection.plate_detector.YoloModel")
    def test_start_raises_when_already_started(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """Calling start() twice raises RuntimeError."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()
        with pytest.raises(RuntimeError, match="already started"):
            service.start()

    @patch("src.detection.plate_detector.YoloModel")
    def test_stop_clears_state(self, mock_yolo_class: MagicMock) -> None:
        """stop() clears model and active cameras."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()
        service.register_camera(1)
        assert service.active_camera_count == 1

        service.stop()
        assert not service.is_started
        assert service.model is None
        assert service.active_camera_count == 0

    @patch("src.detection.plate_detector.YoloModel")
    def test_stop_idempotent(self, mock_yolo_class: MagicMock) -> None:
        """Calling stop() when not started does not raise."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.stop()  # should not raise


class TestPlateDetectionServiceDetect:
    """Tests for single-frame detection."""

    @patch("src.detection.plate_detector.YoloModel")
    def test_detect_raises_if_not_started(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """detect() raises RuntimeError if service not started."""
        service = PlateDetectionService(model_path="models/plate.pt")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with pytest.raises(RuntimeError, match="has not been started"):
            service.detect(frame)

    @patch("src.detection.plate_detector.YoloModel")
    def test_detect_calls_model_predict(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """detect() delegates to the underlying model."""
        mock_model = MagicMock(spec=YoloModel)
        mock_model.predict.return_value = [
            DetectionResult(
                bounding_box=(10, 20, 100, 200),
                confidence=0.95,
                class_id=0,
                class_name="plate",
            ),
        ]
        mock_model.device_name = "cpu"
        mock_model.is_cuda = False
        mock_yolo_class.return_value = mock_model

        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = service.detect(frame, confidence_threshold=0.5)

        assert len(detections) == 1
        assert detections[0].confidence == pytest.approx(0.95)
        mock_model.predict.assert_called_once_with(
            frame,
            confidence_threshold=0.5,
        )


class TestPlateDetectionServiceProcessFrame:
    """Tests for frame processing with event emission."""

    @patch("src.detection.plate_detector.YoloModel")
    def test_process_frame_returns_events(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """process_frame returns PlateDetected events for detections."""
        mock_model = MagicMock(spec=YoloModel)
        mock_model.predict.return_value = [
            DetectionResult(
                bounding_box=(10, 20, 100, 200),
                confidence=0.95,
                class_id=0,
                class_name="plate",
            ),
        ]
        mock_model.device_name = "cpu"
        mock_model.is_cuda = False
        mock_yolo_class.return_value = mock_model

        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()

        frame = _make_dummy_frame(camera_id=7)
        events = service.process_frame(frame)

        assert len(events) == 1
        event = events[0]
        assert event.camera_id == 7
        assert event.bounding_box == (10, 20, 100, 200)
        assert event.confidence == pytest.approx(0.95)
        assert event.timestamp is not None

    @patch("src.detection.plate_detector.YoloModel")
    def test_process_frame_empty_when_no_detections(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """process_frame returns empty list when nothing detected."""
        mock_model = MagicMock(spec=YoloModel)
        mock_model.predict.return_value = []
        mock_model.device_name = "cpu"
        mock_model.is_cuda = False
        mock_yolo_class.return_value = mock_model

        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()

        frame = _make_dummy_frame(camera_id=1)
        events = service.process_frame(frame)
        assert events == []

    @patch("src.detection.plate_detector.YoloModel")
    def test_process_frame_fires_callback(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """process_frame calls on_plate_detected for each detection."""
        mock_model = MagicMock(spec=YoloModel)
        mock_model.predict.return_value = [
            DetectionResult(
                bounding_box=(10, 20, 100, 200),
                confidence=0.95,
                class_id=0,
                class_name="plate",
            ),
            DetectionResult(
                bounding_box=(50, 50, 150, 150),
                confidence=0.80,
                class_id=0,
                class_name="plate",
            ),
        ]
        mock_model.device_name = "cpu"
        mock_model.is_cuda = False
        mock_yolo_class.return_value = mock_model

        callback = MagicMock()
        service = PlateDetectionService(
            model_path="models/plate.pt",
            on_plate_detected=callback,
        )
        service.start()

        frame = _make_dummy_frame(camera_id=1)
        events = service.process_frame(frame)

        assert len(events) == 2
        assert callback.call_count == 2


class TestPlateDetectionServiceThresholds:
    """Tests for per-camera threshold management."""

    def test_set_camera_threshold(self) -> None:
        """set_camera_threshold stores a per-camera override."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.set_camera_threshold(camera_id=3, threshold=0.8)
        assert service.get_camera_threshold(3) == 0.8

    def test_get_camera_threshold_falls_back_to_global(self) -> None:
        """get_camera_threshold returns global if no override set."""
        service = PlateDetectionService(
            model_path="models/plate.pt",
            global_confidence_threshold=0.7,
        )
        assert service.get_camera_threshold(999) == 0.7

    def test_remove_camera_threshold(self) -> None:
        """remove_camera_threshold clears the override."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.set_camera_threshold(camera_id=3, threshold=0.8)
        service.remove_camera_threshold(3)
        assert service.get_camera_threshold(3) == 0.5  # global default

    def test_set_camera_threshold_invalid(self) -> None:
        """Setting an invalid per-camera threshold raises ValueError."""
        service = PlateDetectionService(model_path="models/plate.pt")
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            service.set_camera_threshold(1, -0.1)
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            service.set_camera_threshold(1, 1.5)

    @patch("src.detection.plate_detector.YoloModel")
    def test_global_threshold_setter_updates_model(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """Setting global threshold updates the model's threshold."""
        mock_model = MagicMock(spec=YoloModel)
        mock_model.device_name = "cpu"
        mock_model.is_cuda = False
        mock_yolo_class.return_value = mock_model

        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()

        service.global_confidence_threshold = 0.9
        assert service.global_confidence_threshold == 0.9
        assert mock_model.confidence_threshold == 0.9


class TestPlateDetectionServiceCameras:
    """Tests for camera registration and multi-camera processing."""

    def test_register_camera(self) -> None:
        """register_camera adds to active cameras."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.register_camera(1)
        service.register_camera(2)
        assert service.active_camera_count == 2

    def test_unregister_camera(self) -> None:
        """unregister_camera removes from active cameras."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.register_camera(1)
        service.register_camera(2)
        service.unregister_camera(1)
        assert service.active_camera_count == 1

    def test_unregister_unknown_camera_does_not_raise(self) -> None:
        """unregister_camera on unregistered camera is safe."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.unregister_camera(999)  # should not raise

    @patch("src.detection.plate_detector.YoloModel")
    def test_process_frames_skips_unregistered_cameras(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """process_frames ignores frames from unregistered cameras."""
        mock_model = MagicMock(spec=YoloModel)
        mock_model.predict.return_value = [
            DetectionResult(
                bounding_box=(10, 20, 100, 200),
                confidence=0.95,
                class_id=0,
                class_name="plate",
            ),
        ]
        mock_model.device_name = "cpu"
        mock_model.is_cuda = False
        mock_yolo_class.return_value = mock_model

        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()
        service.register_camera(1)  # only camera 1 is registered

        frames = [
            _make_dummy_frame(camera_id=1),  # registered
            _make_dummy_frame(camera_id=2),  # NOT registered
        ]
        results = service.process_frames(frames)

        assert 1 in results
        assert 2 not in results


class TestPlateDetectionServiceAnnotate:
    """Tests for frame annotation."""

    def test_annotate_frame_returns_colored_frame(self) -> None:
        """annotate_frame returns a BGR frame with boxes drawn."""
        service = PlateDetectionService(model_path="models/plate.pt")

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        detections = [
            DetectionResult(
                bounding_box=(10, 20, 50, 60),
                confidence=0.95,
                class_id=0,
                class_name="plate",
            ),
        ]
        annotated = service.annotate_frame(frame, detections)
        assert annotated.shape == frame.shape
        assert annotated.dtype == frame.dtype
        # The annotated frame should differ from the original
        # (bounding box drawn)
        assert not np.array_equal(annotated, frame)


class TestPlateDetectionServiceWarmup:
    """Tests for model warmup."""

    @patch("src.detection.plate_detector.YoloModel")
    def test_warmup_runs_inference(
        self,
        mock_yolo_class: MagicMock,
    ) -> None:
        """warmup() runs predict on a dummy frame."""
        mock_model = MagicMock(spec=YoloModel)
        mock_model.predict.return_value = []
        mock_model.device_name = "cpu"
        mock_model.is_cuda = False
        mock_yolo_class.return_value = mock_model

        service = PlateDetectionService(model_path="models/plate.pt")
        service.start()

        service.warmup()
        mock_model.predict.assert_called_once()
        # The confidence_threshold should be 1.0 for warmup
        assert mock_model.predict.call_args[1]["confidence_threshold"] == 1.0

    def test_warmup_safe_when_not_started(self) -> None:
        """warmup() does nothing when service is not started."""
        service = PlateDetectionService(model_path="models/plate.pt")
        service.warmup()  # should not raise


# ======================================================================
# Bounding-box renderer
# ======================================================================


class TestDrawDetections:
    """Tests for draw_detections function."""

    @pytest.fixture
    def frame(self) -> np.ndarray:
        return np.zeros((200, 300, 3), dtype=np.uint8)

    @pytest.fixture
    def detections(self) -> List[DetectionResult]:
        return [
            DetectionResult(
                bounding_box=(10, 20, 100, 80),
                confidence=0.95,
                class_id=0,
                class_name="plate",
            ),
        ]

    def test_returns_new_array(self, frame: np.ndarray, detections: List[DetectionResult]) -> None:
        """draw_detections returns a new array, not the input."""
        result = draw_detections(frame, detections)
        assert result is not frame

    def test_annotated_frame_differs(self, frame: np.ndarray, detections: List[DetectionResult]) -> None:
        """Annotated frame has different pixel values (boxes drawn)."""
        result = draw_detections(frame, detections)
        assert not np.array_equal(result, frame)

    def test_empty_detections_returns_copy(self, frame: np.ndarray) -> None:
        """With no detections, a copy of the frame is returned."""
        result = draw_detections(frame, [])
        assert result is not frame
        np.testing.assert_array_equal(result, frame)

    def test_returns_three_channel(self, frame: np.ndarray, detections: List[DetectionResult]) -> None:
        """Result has the same shape as input."""
        result = draw_detections(frame, detections)
        assert result.shape == frame.shape
        assert result.shape[2] == 3


class TestDrawDetectionCenters:
    """Tests for draw_detection_centers function."""

    @pytest.fixture
    def frame(self) -> np.ndarray:
        return np.zeros((200, 300, 3), dtype=np.uint8)

    def test_returns_new_array(self, frame: np.ndarray) -> None:
        """draw_detection_centers returns a new array."""
        detections = [
            DetectionResult(bounding_box=(50, 50, 150, 150)),
        ]
        result = draw_detection_centers(frame, detections)
        assert result is not frame

    def test_empty_detections(self, frame: np.ndarray) -> None:
        """With no detections, returns a copy."""
        result = draw_detection_centers(frame, [])
        np.testing.assert_array_equal(result, frame)


class TestCropDetections:
    """Tests for crop_detections function."""

    def test_crops_multiple_detections(self) -> None:
        """crop_detections returns a crop for each detection."""
        frame = np.ones((200, 300, 3), dtype=np.uint8) * 128
        detections = [
            DetectionResult(bounding_box=(10, 10, 50, 50)),
            DetectionResult(bounding_box=(100, 100, 150, 150)),
        ]
        crops = crop_detections(frame, detections)
        assert len(crops) == 2
        assert crops[0].shape == (40, 40, 3)
        assert crops[1].shape == (50, 50, 3)

    def test_empty_detections(self) -> None:
        """No detections returns empty list."""
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        assert crop_detections(frame, []) == []

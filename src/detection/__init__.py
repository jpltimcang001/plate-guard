"""Detection infrastructure — YOLO, frame capture, USB enumeration, zone validation.

Components
----------
- ``FrameQueue`` — Thread-safe bounded frame queue with oldest-drop.
- ``FpsMonitor`` — Rolling-window frames-per-second calculation.
- ``FrameCapture`` — OpenCV-based RTSP/USB background capture thread.
- ``CameraHealthMonitor`` — Watchdog with auto-reconnect for stream health.
- ``UsbEnumerator`` — USB camera device enumeration via OpenCV.
- ``YoloModel`` — YOLOv8 model wrapper with GPU/CPU fallback.
- ``PlateDetectionService`` — High-level detection orchestration.
- ``DetectionResult`` — Domain entity for a single detection.
- ``draw_detections`` — Bounding-box annotation utility.
- ``point_in_polygon`` — Ray-casting point-in-polygon test.
- ``compute_iou`` — Intersection-over-Union for bounding boxes.
- ``ZoneValidator`` — Zone-aware detection filtering.
- ``DetectionTracker`` — IOU-based cross-frame tracking.
- ``DuplicateFilter`` — Cooldown-based plate text deduplication.
- ``DetectionPipeline`` — Full frame-to-log orchestration.
"""

from src.detection.bbox_renderer import (
    crop_detections,
    draw_detection_centers,
    draw_detections,
)
from src.detection.camera_health import CameraHealthMonitor, HealthSnapshot
from src.detection.detection_result import DetectionResult
from src.detection.duplicate_filter import DuplicateFilter
from src.detection.fps_monitor import FpsMonitor
from src.detection.frame_capture import CaptureStats, FrameCapture
from src.detection.frame_queue import Frame, FrameQueue
from src.detection.geometry import compute_iou, point_in_polygon
from src.detection.pipeline import DetectionEvent, DetectionPipeline, PipelineResult
from src.detection.plate_detector import PlateDetectionService
from src.detection.tracker import DetectionTracker, TrackedObject
from src.detection.usb_enumerator import UsbEnumerator
from src.detection.yolo_model import YoloModel
from src.detection.zone_validator import ZoneValidator

__all__ = [
    "CameraHealthMonitor",
    "CaptureStats",
    "compute_iou",
    "crop_detections",
    "DetectionEvent",
    "DetectionPipeline",
    "DetectionResult",
    "DetectionTracker",
    "draw_detection_centers",
    "draw_detections",
    "DuplicateFilter",
    "FpsMonitor",
    "Frame",
    "FrameCapture",
    "FrameQueue",
    "HealthSnapshot",
    "PipelineResult",
    "PlateDetectionService",
    "point_in_polygon",
    "TrackedObject",
    "UsbEnumerator",
    "YoloModel",
    "ZoneValidator",
]

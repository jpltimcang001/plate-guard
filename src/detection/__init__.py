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
"""

from src.detection.bbox_renderer import (
    crop_detections,
    draw_detection_centers,
    draw_detections,
)
from src.detection.camera_health import CameraHealthMonitor, HealthSnapshot
from src.detection.detection_result import DetectionResult
from src.detection.fps_monitor import FpsMonitor
from src.detection.frame_capture import CaptureStats, FrameCapture
from src.detection.frame_queue import Frame, FrameQueue
from src.detection.plate_detector import PlateDetectionService
from src.detection.usb_enumerator import UsbEnumerator
from src.detection.yolo_model import YoloModel

__all__ = [
    "CameraHealthMonitor",
    "CaptureStats",
    "crop_detections",
    "DetectionResult",
    "draw_detection_centers",
    "draw_detections",
    "FpsMonitor",
    "Frame",
    "FrameCapture",
    "FrameQueue",
    "HealthSnapshot",
    "PlateDetectionService",
    "UsbEnumerator",
    "YoloModel",
]

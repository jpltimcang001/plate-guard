"""Detection infrastructure — YOLO, frame capture, USB enumeration, zone validation.

All components should be imported directly from their submodules
(e.g. ``from src.detection.frame_capture import FrameCapture``)
rather than from this package, to avoid circular dependencies.
"""

from src.detection.geometry import compute_iou, point_in_polygon

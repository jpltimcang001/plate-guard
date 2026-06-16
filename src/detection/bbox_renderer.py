"""Bounding-box rendering utilities for detection results.

Provides functions to draw bounding boxes, labels, and confidence
scores onto frames.  All drawing is done via OpenCV for performance.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from src.detection.detection_result import DetectionResult


# Default colour palette for different class IDs (BGR format).
# These are visually distinct colours for up to 10 classes.
_DEFAULT_COLORS: List[Tuple[int, int, int]] = [
    (0, 255, 0),      # green
    (255, 0, 0),      # blue
    (0, 0, 255),      # red
    (255, 255, 0),    # cyan
    (255, 0, 255),    # magenta
    (0, 255, 255),    # yellow
    (128, 0, 0),      # navy
    (0, 128, 0),      # dark green
    (0, 0, 128),      # maroon
    (128, 128, 0),    # olive
]


def _get_color(class_id: int, palette: Optional[List[Tuple[int, int, int]]] = None) -> Tuple[int, int, int]:
    """Return a deterministic colour for a given class ID.

    Args:
        class_id: The model's class integer ID.
        palette: Optional custom colour palette (BGR tuples).

    Returns:
        A BGR colour tuple.

    """
    colors = palette or _DEFAULT_COLORS
    return colors[class_id % len(colors)]


def draw_detections(
    frame: np.ndarray,
    detections: List[DetectionResult],
    *,
    show_label: bool = True,
    show_confidence: bool = True,
    box_thickness: int = 2,
    label_bg_alpha: float = 0.6,
    label_font_scale: float = 0.5,
    label_padding: int = 2,
    color_palette: Optional[List[Tuple[int, int, int]]] = None,
) -> np.ndarray:
    """Draw bounding boxes and labels for a list of detections.

    The input frame is **not** modified; a new annotated frame is
    returned.

    Args:
        frame: Original BGR frame as a numpy array ``(H, W, 3)``.
        detections: List of ``DetectionResult`` to draw.
        show_label: Whether to draw the class label above the box.
        show_confidence: Whether to include the confidence percentage.
        box_thickness: Pixel width of the bounding-box outline.
        label_bg_alpha: Opacity of the label background rectangle
            (``0.0`` = fully transparent, ``1.0`` = fully opaque).
        label_font_scale: Font scale for label text.
        label_padding: Padding in pixels around label text.
        color_palette: Optional list of BGR colour tuples for classes.

    Returns:
        A new BGR frame with annotations drawn on it.

    """
    if not detections:
        return frame.copy()

    result = frame.copy()
    overlay = result.copy() if label_bg_alpha < 1.0 else result

    for detection in detections:
        x1, y1, x2, y2 = detection.bounding_box
        color = _get_color(detection.class_id, color_palette)

        # --- Draw bounding box ---
        cv2.rectangle(
            img=overlay,
            pt1=(x1, y1),
            pt2=(x2, y2),
            color=color,
            thickness=box_thickness,
            lineType=cv2.LINE_AA,
        )

        # --- Build label text ---
        label_parts: List[str] = []
        if show_label and detection.class_name:
            label_parts.append(detection.class_name)
        if show_confidence:
            label_parts.append(f"{detection.confidence * 100:.1f}%")
        label_text = " ".join(label_parts)

        if not label_text:
            continue

        # --- Draw label background ---
        (label_w, label_h), _ = cv2.getTextSize(
            text=label_text,
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=label_font_scale,
            thickness=1,
        )
        label_x1 = x1
        label_y1 = y1 - label_h - 2 * label_padding
        label_x2 = x1 + label_w + 2 * label_padding
        label_y2 = y1

        # If the label would go above the frame, draw it below the box
        if label_y1 < 0:
            label_y1 = y2 + 2
            label_y2 = y2 + label_h + 2 * label_padding

        if label_bg_alpha >= 1.0:
            cv2.rectangle(
                img=overlay,
                pt1=(label_x1, label_y1),
                pt2=(label_x2, label_y2),
                color=color,
                thickness=cv2.FILLED,
            )
        else:
            # Semi-transparent background using overlay blending
            sub_overlay = overlay[label_y1:label_y2, label_x1:label_x2]
            cv2.rectangle(
                img=sub_overlay,
                pt1=(0, 0),
                pt2=(label_x2 - label_x1, label_y2 - label_y1),
                color=color,
                thickness=cv2.FILLED,
            )
            alpha = label_bg_alpha
            result[label_y1:label_y2, label_x1:label_x2] = cv2.addWeighted(
                sub_overlay,
                alpha,
                result[label_y1:label_y2, label_x1:label_x2],
                1.0 - alpha,
                0,
            )
            continue  # text is drawn below

        # --- Draw label text ---
        text_x = label_x1 + label_padding
        text_y = label_y2 - label_padding
        cv2.putText(
            img=overlay,
            text=label_text,
            org=(text_x, text_y),
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=label_font_scale,
            color=(255, 255, 255),  # white text
            thickness=1,
            lineType=cv2.LINE_AA,
        )

    # If we used overlay for semi-transparency, blend it now
    if label_bg_alpha < 1.0 and detections:
        cv2.addWeighted(overlay, label_bg_alpha, result, 1.0 - label_bg_alpha, 0, result)

    return result


def draw_detection_centers(
    frame: np.ndarray,
    detections: List[DetectionResult],
    *,
    radius: int = 4,
    color: Tuple[int, int, int] = (0, 255, 255),
    thickness: int = -1,
) -> np.ndarray:
    """Draw a small circle at the centre of each detection bounding box.

    Args:
        frame: Original BGR frame.
        detections: List of detections.
        radius: Circle radius in pixels.
        color: BGR colour tuple.
        thickness: Circle thickness (``-1`` = filled).

    Returns:
        A new BGR frame with centre markers.

    """
    result = frame.copy()
    for detection in detections:
        cx, cy = detection.center
        cv2.circle(
            img=result,
            center=(int(cx), int(cy)),
            radius=radius,
            color=color,
            thickness=thickness,
            lineType=cv2.LINE_AA,
        )
    return result


def crop_detections(
    frame: np.ndarray,
    detections: List[DetectionResult],
) -> List[np.ndarray]:
    """Crop each detection's region of interest from the frame.

    Args:
        frame: Original BGR frame.
        detections: List of detections.

    Returns:
        A list of cropped sub-images in the same order as detections.

    """
    return [detection.crop_frame(frame) for detection in detections]

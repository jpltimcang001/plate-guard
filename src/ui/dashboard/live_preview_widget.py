"""Live camera preview widget.

Displays video frames from a camera in real time.  Frames are
obtained via a callable callback that the capture pipeline
invokes on every frame.
"""

from __future__ import annotations

from typing import Callable, Optional

import cv2
import numpy as np
from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class LivePreviewWidget(QWidget):
    """Displays a live camera feed.

    The widget polls a *frame source* at a configurable interval.
    The frame source is a zero-argument callable that returns
    either a BGR numpy array or ``None``.

    If no frame source is set, a placeholder message is shown.

    Usage::

        preview = LivePreviewWidget(parent=self)
        preview.set_frame_source(my_camera.get_latest_frame)
        preview.start()
    """

    DEFAULT_POLL_MS = 33  # ≈30 FPS
    PLACEHOLDER_TEXT = "No camera selected"
    NO_SOURCE_TEXT = "No frame source configured"

    def __init__(
        self,
        parent: QWidget | None = None,
        poll_interval_ms: int = DEFAULT_POLL_MS,
    ) -> None:
        """Initialise the live preview widget.

        Args:
            parent: Optional parent widget.
            poll_interval_ms: Milliseconds between frame polls
                (default 33 ms ≈ 30 FPS).

        """
        super().__init__(parent=parent)

        self._frame_source: Callable[[], Optional[np.ndarray]] | None = None
        self._poll_interval = poll_interval_ms
        self._camera_name: str = ""
        self._frame_count: int = 0

        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_frame)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def camera_name(self) -> str:
        """Name of the camera currently being previewed."""
        return self._camera_name

    @property
    def frame_count(self) -> int:
        """Total number of frames displayed since the source was set."""
        return self._frame_count

    @property
    def is_running(self) -> bool:
        """Whether the polling timer is active."""
        return self._timer.isActive()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_frame_source(
        self,
        source: Callable[[], Optional[np.ndarray]] | None,
        camera_name: str = "",
    ) -> None:
        """Set the callback that provides the latest frame.

        Args:
            source: A zero-argument callable that returns a BGR numpy
                array or ``None``.  Pass ``None`` to disconnect.
            camera_name: Optional display name for the camera.

        """
        self._frame_source = source
        self._camera_name = camera_name
        self._frame_count = 0

        if source is None:
            self._show_placeholder(self.NO_SOURCE_TEXT)
        else:
            self._show_placeholder(f"Waiting for {camera_name or 'camera'}…")

    def start(self) -> None:
        """Begin polling the frame source."""
        if self._frame_source is None:
            logger.warning("LivePreviewWidget.start() called with no frame source")
            return
        if not self._timer.isActive():
            self._timer.start(self._poll_interval)
            logger.debug(
                "LivePreviewWidget started (poll={}ms, camera={!r})",
                self._poll_interval,
                self._camera_name,
            )

    def stop(self) -> None:
        """Stop polling the frame source."""
        if self._timer.isActive():
            self._timer.stop()
            logger.debug("LivePreviewWidget stopped")

    def set_poll_interval(self, interval_ms: int) -> None:
        """Change the frame polling interval.

        Args:
            interval_ms: New interval in milliseconds (≥ 16).

        """
        interval_ms = max(16, interval_ms)
        self._poll_interval = interval_ms
        if self._timer.isActive():
            self._timer.setInterval(interval_ms)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._image_label.setMinimumSize(320, 240)
        self._image_label.setStyleSheet(
            "QLabel { background-color: #1a1a1a; color: #888; "
            "border: 1px solid #333; font-size: 14px; }",
        )
        self._show_placeholder(self.PLACEHOLDER_TEXT)

        layout.addWidget(self._image_label)

    def _show_placeholder(self, text: str) -> None:
        """Display centred placeholder text.

        The pixmap is cleared so that only the placeholder text
        is visible.
        """
        self._image_label.clear()
        self._image_label.setText(text)

    def _poll_frame(self) -> None:
        """Called by the timer — fetch and display the latest frame."""
        if self._frame_source is None:
            self.stop()
            self._show_placeholder(self.NO_SOURCE_TEXT)
            return

        try:
            frame = self._frame_source()
        except Exception:
            logger.opt(exception=True).warning(
                "LivePreviewWidget frame source raised an exception",
            )
            return

        if frame is None or frame.size == 0:
            return

        self._display_frame(frame)
        self._frame_count += 1

    def _display_frame(self, frame: np.ndarray) -> None:
        """Convert a BGR frame to a QPixmap and display it.

        Args:
            frame: BGR image as a numpy array ``(H, W, 3)``.

        """
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        qimage = QImage(
            rgb_frame.data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(qimage)

        # Scale to fit the label while maintaining aspect ratio
        scaled = pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    def __repr__(self) -> str:
        return (
            f"<LivePreviewWidget camera={self._camera_name!r} "
            f"running={self.is_running} frames={self._frame_count}>"
        )

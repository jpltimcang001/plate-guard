"""Writes snapshot images and video clips to disk.

Uses OpenCV for both JPEG encoding and MP4 video writing.
Directory creation is handled automatically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
from loguru import logger


class MediaWriter:
    """File I/O for detection evidence.

    Usage::

        writer = MediaWriter(base_dir="./media")
        snap_path = writer.save_snapshot(frame, camera_id=1, plate_text="ABC123")
        clip_path = writer.save_clip(frames, camera_id=1, plate_text="ABC123", fps=30)
    """

    SNAPSHOT_DIR = "snapshots"
    CLIP_DIR = "clips"
    SNAPSHOT_QUALITY = 95  # JPEG quality 0–100
    VIDEO_CODEC = "avc1"   # H.264; fallback to "mp4v" if unavailable

    def __init__(self, base_dir: str | Path = "media") -> None:
        """Initialise the media writer.

        Args:
            base_dir: Root directory under which ``snapshots/`` and
                ``clips/`` subdirectories are created.

        """
        self._base_dir = Path(base_dir)
        self._snapshot_dir = self._base_dir / self.SNAPSHOT_DIR
        self._clip_dir = self._base_dir / self.CLIP_DIR

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def base_dir(self) -> Path:
        """Root media directory."""
        return self._base_dir

    @property
    def snapshot_dir(self) -> Path:
        """Directory where snapshot JPEGs are stored."""
        return self._snapshot_dir

    @property
    def clip_dir(self) -> Path:
        """Directory where video clip MP4s are stored."""
        return self._clip_dir

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def save_snapshot(
        self,
        frame: np.ndarray,
        camera_id: int,
        timestamp: float,
        plate_text: str = "",
    ) -> str:
        """Save a single frame as a JPEG snapshot.

        Args:
            frame: BGR image as a numpy array ``(H, W, 3)``.
            camera_id: Source camera ID (used in filename).
            timestamp: Unix timestamp (used in filename).
            plate_text: Optional recognised plate text for filename.

        Returns:
            Absolute filesystem path to the saved JPEG file.

        Raises:
            ValueError: If the frame is empty or has an invalid format.
            OSError: If the directory cannot be created or the file
                cannot be written.

        """
        if frame is None or frame.size == 0:
            raise ValueError("Cannot save snapshot: frame is empty")

        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(
                f"Cannot save snapshot: expected 3-channel BGR, got shape {frame.shape}",
            )

        self._ensure_dirs()
        filename = self._build_snapshot_filename(camera_id, timestamp, plate_text)
        filepath = self._snapshot_dir / filename

        success, jpeg_bytes = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, self.SNAPSHOT_QUALITY],
        )
        if not success:
            raise OSError("cv2.imencode failed to encode snapshot as JPEG")

        filepath.write_bytes(jpeg_bytes.tobytes())

        logger.debug(
            "Snapshot saved: {} ({} bytes, {}x{})",
            filepath,
            len(jpeg_bytes),
            frame.shape[1],
            frame.shape[0],
        )
        return str(filepath.resolve())

    # ------------------------------------------------------------------
    # Video clip
    # ------------------------------------------------------------------

    def save_clip(
        self,
        frames: List[np.ndarray],
        camera_id: int,
        timestamp: float,
        plate_text: str = "",
        fps: float = 30.0,
    ) -> str:
        """Write a list of BGR frames to an MP4 video file.

        Args:
            frames: Ordered list of BGR frames (oldest first).
            camera_id: Source camera ID (used in filename).
            timestamp: Unix timestamp of the detection (used in
                filename).
            plate_text: Optional recognised plate text for filename.
            fps: Output video frame rate (default 30).

        Returns:
            Absolute path to the saved MP4 file.

        Raises:
            ValueError: If ``frames`` is empty.
            OSError: If the video cannot be written.

        """
        if not frames:
            raise ValueError("Cannot save clip: frame list is empty")

        self._ensure_dirs()
        filename = self._build_clip_filename(camera_id, timestamp, plate_text)
        filepath = self._clip_dir / filename

        height, width = frames[0].shape[:2]

        # Try H.264 first, fall back to MP4V
        codec = cv2.VideoWriter_fourcc(*self.VIDEO_CODEC)
        writer = cv2.VideoWriter(
            str(filepath),
            codec,
            fps,
            (width, height),
        )
        if not writer.isOpened():
            logger.debug(
                "Codec {} not available, falling back to 'mp4v'",
                self.VIDEO_CODEC,
            )
            codec = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(
                str(filepath),
                codec,
                fps,
                (width, height),
            )
            if not writer.isOpened():
                raise OSError(
                    f"Failed to open VideoWriter for {filepath}",
                )

        for frame in frames:
            writer.write(frame)

        writer.release()

        file_size = filepath.stat().st_size if filepath.exists() else 0
        logger.debug(
            "Clip saved: {} ({} frames, {} bytes, {}x{} @ {:.1f} FPS)",
            filepath,
            len(frames),
            file_size,
            width,
            height,
            fps,
        )
        return str(filepath.resolve())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        """Create snapshot and clip directories if they don't exist."""
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._clip_dir.mkdir(parents=True, exist_ok=True)

    def _build_snapshot_filename(
        self,
        camera_id: int,
        timestamp: float,
        plate_text: str = "",
    ) -> str:
        """Build a unique filename for a snapshot.

        Format: ``snap_{camera_id}_{timestamp}_{plate}.jpg``
        """
        ts_str = f"{timestamp:.3f}".replace(".", "_")
        label = f"_{plate_text}" if plate_text else ""
        return f"snap_{camera_id}_{ts_str}{label}.jpg"

    def _build_clip_filename(
        self,
        camera_id: int,
        timestamp: float,
        plate_text: str = "",
    ) -> str:
        """Build a unique filename for a video clip.

        Format: ``clip_{camera_id}_{timestamp}_{plate}.mp4``
        """
        ts_str = f"{timestamp:.3f}".replace(".", "_")
        label = f"_{plate_text}" if plate_text else ""
        return f"clip_{camera_id}_{ts_str}{label}.mp4"

    def __repr__(self) -> str:
        return (
            f"<MediaWriter base_dir={self._base_dir.resolve()!s}>"
        )

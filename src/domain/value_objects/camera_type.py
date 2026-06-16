"""CameraType enumeration."""

from __future__ import annotations

import enum


class CameraType(enum.Enum):
    """Supported camera source types."""

    RTSP = "rtsp"
    USB = "usb"

    def __str__(self) -> str:
        return self.value

"""CameraStatus enumeration for stream health state."""

from __future__ import annotations

import enum


class CameraStatus(enum.Enum):
    """Represents the current health state of a camera stream."""

    ONLINE = "online"
    """Camera is connected and frames are being received."""

    OFFLINE = "offline"
    """Camera is disconnected and not attempting to reconnect."""

    RECONNECTING = "reconnecting"
    """Camera stream was lost; a reconnection attempt is in progress."""

    ERROR = "error"
    """Camera encountered a non-recoverable error."""

    DISABLED = "disabled"
    """Camera is intentionally disabled by the user."""

    def __str__(self) -> str:
        return self.value

    @property
    def is_active(self) -> bool:
        """Return ``True`` if the camera is expected to produce frames."""
        return self in (CameraStatus.ONLINE, CameraStatus.RECONNECTING)

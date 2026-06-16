"""Application-layer exceptions."""

from src.application.exceptions.camera_errors import (
    CameraConnectionError,
    CameraNotFoundError,
    DuplicateNameError,
)

__all__ = [
    "CameraNotFoundError",
    "DuplicateNameError",
    "CameraConnectionError",
]

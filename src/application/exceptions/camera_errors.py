"""Camera-specific application exceptions."""

from __future__ import annotations


class CameraNotFoundError(LookupError):
    """Raised when a camera with the given ID does not exist."""

    def __init__(self, camera_id: int) -> None:
        self.camera_id = camera_id
        super().__init__(f"Camera with id={camera_id} not found.")


class DuplicateNameError(ValueError):
    """Raised when a camera name already exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A camera with name={name!r} already exists.")


class CameraConnectionError(RuntimeError):
    """Raised when the camera stream cannot be reached or validated."""

    def __init__(self, camera_id: int | None, detail: str = "") -> None:
        self.camera_id = camera_id
        message = f"Camera connection failed"
        if camera_id is not None:
            message += f" for camera id={camera_id}"
        if detail:
            message += f": {detail}"
        super().__init__(message)

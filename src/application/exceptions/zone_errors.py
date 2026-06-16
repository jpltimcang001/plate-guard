"""Zone-specific application exceptions."""

from __future__ import annotations


class ZoneNotFoundError(LookupError):
    """Raised when a zone with the given ID does not exist."""

    def __init__(self, zone_id: int) -> None:
        self.zone_id = zone_id
        super().__init__(f"Zone with id={zone_id} not found.")


class DuplicateZoneNameError(ValueError):
    """Raised when a zone name already exists within the same camera."""

    def __init__(self, name: str, camera_id: int) -> None:
        self.name = name
        self.camera_id = camera_id
        super().__init__(
            f"A zone with name={name!r} already exists for camera id={camera_id}."
        )

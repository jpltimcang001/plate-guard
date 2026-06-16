"""Zone validation — point-in-polygon tests for detection zones.

Provides:
- ``ZoneValidator`` service that caches zones per camera and tests
  whether a detection's center point falls within any enabled zone.

Uses the ray-casting algorithm from ``src.detection.geometry``.
"""

from __future__ import annotations

from typing import Dict, List

from loguru import logger

from src.detection.detection_result import DetectionResult
from src.detection.geometry import point_in_polygon
from src.domain.entities.zone import Zone


class ZoneValidator:
    """Validates whether detections fall within any configured zone.

    Caches zones per camera to avoid repeated database lookups.
    Thread-safe if the zone list is updated atomically.

    Usage::

        validator = ZoneValidator(zone_service)
        validator.refresh_zones(camera_id=1)

        for det in detections:
            if validator.is_in_any_zone(camera_id=1, detection=det):
                process(det)
    """

    def __init__(self, zone_service: "ZoneService | None" = None) -> None:  # noqa: F821
        """Initialise the zone validator.

        Args:
            zone_service: Optional ``ZoneService`` for loading zones.
                If ``None``, zones must be provided via ``set_zones``
                or ``refresh_zones`` will raise.

        """
        self._zone_service = zone_service
        # camera_id -> list of Zone
        self._zone_cache: Dict[int, List[Zone]] = {}

    # ------------------------------------------------------------------
    # Zone management
    # ------------------------------------------------------------------

    def refresh_zones(self, camera_id: int) -> None:
        """Reload zones for a camera from the database.

        Args:
            camera_id: The camera to refresh zones for.

        Raises:
            RuntimeError: If no ``zone_service`` was provided.

        """
        if self._zone_service is None:
            raise RuntimeError(
                "ZoneValidator has no zone_service; "
                "use set_zones() or provide a zone_service at init.",
            )

        zones = self._zone_service.get_zones_by_camera(camera_id)
        self._zone_cache[camera_id] = [
            Zone(
                id=z.id,
                camera_id=z.camera_id,
                name=z.name,
                points=list(z.points),
            )
            for z in zones
        ]
        logger.debug(
            "ZoneValidator refreshed {} zone(s) for camera {}",
            len(zones),
            camera_id,
        )

    def set_zones(self, camera_id: int, zones: list[Zone]) -> None:
        """Set zones for a camera directly (bypasses DB).

        Args:
            camera_id: The camera ID.
            zones: List of ``Zone`` domain entities.

        """
        self._zone_cache[camera_id] = list(zones)

    def clear_cache(self, camera_id: int | None = None) -> None:
        """Clear the zone cache for one or all cameras.

        Args:
            camera_id: If provided, clear only this camera's cache.
                If ``None``, clear all cached zones.

        """
        if camera_id is not None:
            self._zone_cache.pop(camera_id, None)
        else:
            self._zone_cache.clear()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def get_zones_for_camera(self, camera_id: int) -> list[Zone]:
        """Return cached zones for a camera (auto-refresh if empty).

        Args:
            camera_id: The camera ID.

        Returns:
            A list of ``Zone`` instances.

        """
        if camera_id not in self._zone_cache or not self._zone_cache[camera_id]:
            try:
                self.refresh_zones(camera_id)
            except RuntimeError:
                return []
        return self._zone_cache.get(camera_id, [])

    def is_in_any_zone(
        self,
        camera_id: int,
        detection: DetectionResult,
    ) -> bool:
        """Check whether a detection's centre lies in any enabled zone.

        Args:
            camera_id: The camera that produced the frame.
            detection: The detection result to test.

        Returns:
            ``True`` if the centre point of the detection is inside
            at least one zone for this camera. Returns ``True`` if
            the camera has no zones configured (allow all).

        """
        zones = self.get_zones_for_camera(camera_id)

        # No zones configured → allow all detections
        if not zones:
            return True

        cx, cy = detection.center

        for zone in zones:
            if point_in_polygon(cx, cy, zone.points):
                return True

        return False

    def which_zones(
        self,
        camera_id: int,
        detection: DetectionResult,
    ) -> list[Zone]:
        """Return all zones that contain the detection's centre.

        Args:
            camera_id: The camera ID.
            detection: The detection result.

        Returns:
            A list of matching zones (empty if none match).

        """
        zones = self.get_zones_for_camera(camera_id)
        if not zones:
            return []

        cx, cy = detection.center
        return [z for z in zones if point_in_polygon(cx, cy, z.points)]

    def __repr__(self) -> str:
        return (
            f"<ZoneValidator cameras={len(self._zone_cache)}>"
        )

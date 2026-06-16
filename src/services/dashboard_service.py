"""Dashboard service — aggregates data for the Dashboard UI.

Queries multiple repositories to produce a single ``DashboardData``
snapshot that the presentation layer can render without further
database access.
"""

from __future__ import annotations

from datetime import datetime, time as dt_time

from loguru import logger

from src.application.dto.dashboard_dto import (
    CameraStatusDTO,
    DashboardData,
    DetectionSummaryDTO,
)
from src.database.models import DetectionModel
from src.repositories.detection_repository import DetectionFilter, DetectionRepository
from src.services.camera_service import CameraService


class DashboardService:
    """Service that produces consolidated dashboard data.

    Usage::

        service = DashboardService(camera_service, detection_repo)
        data = service.refresh()
        # data.cameras, data.total_detections_today, …
    """

    RECENT_DETECTIONS_LIMIT = 20

    def __init__(
        self,
        camera_service: CameraService,
        detection_repository: DetectionRepository,
    ) -> None:
        """Initialise the dashboard service.

        Args:
            camera_service: The ``CameraService`` instance (provides
                camera list and status).
            detection_repository: The ``DetectionRepository`` instance
                (provides detection counts and recent records).

        """
        self._camera_service = camera_service
        self._detection_repo = detection_repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> DashboardData:
        """Build a complete snapshot of the current dashboard state.

        Queries the camera list, detection counts for today, and
        recent detection records in a single call.

        Returns:
            A ``DashboardData`` instance ready for the UI.

        """
        cameras_dto = self._camera_service.get_all_cameras()

        # Build detection count filter for today
        midnight = datetime.combine(datetime.now().date(), dt_time.min)
        today_filter = DetectionFilter(
            date_from=midnight,
            limit=1_000_000,  # effectively unlimited
        )

        total_today = self._detection_repo.count_filtered(today_filter)

        # Per-camera counts
        count_by_camera: dict[int, int] = {}
        for cam in cameras_dto:
            cam_filter = DetectionFilter(camera_id=cam.id, date_from=midnight)
            count_by_camera[cam.id] = self._detection_repo.count_filtered(cam_filter)

        # Recent detections
        recent_filter = DetectionFilter(limit=self.RECENT_DETECTIONS_LIMIT)
        recent_models = self._detection_repo.get_filtered(recent_filter)

        # Build camera lookup for resolving names
        camera_names: dict[int, str] = {c.id: c.name for c in cameras_dto}

        recent: list[DetectionSummaryDTO] = [
            self._detection_to_summary(m, camera_names) for m in recent_models
        ]

        # Camera statuses
        status_dtos: list[CameraStatusDTO] = []
        for cam in cameras_dto:
            status_dtos.append(
                CameraStatusDTO(
                    id=cam.id,
                    name=cam.name,
                    camera_type=cam.camera_type,
                    enabled=cam.enabled,
                    status=self._derive_status(cam.enabled),
                    detection_count_today=count_by_camera.get(cam.id, 0),
                ),
            )

        # Aggregate counts
        online = sum(1 for s in status_dtos if s.status == "online" and s.enabled)
        offline = sum(
            1 for s in status_dtos if s.status != "online" and s.enabled
        )
        disabled_count = sum(1 for s in status_dtos if not s.enabled)

        return DashboardData(
            cameras=status_dtos,
            total_detections_today=total_today,
            detection_count_by_camera=count_by_camera,
            recent_detections=recent,
            cameras_online=online,
            cameras_offline=offline,
            cameras_disabled=disabled_count,
            refreshed_at=datetime.now(),
        )

    def get_camera_names(self) -> dict[int, str]:
        """Return a ``camera_id → name`` lookup map.

        Returns:
            A dict mapping camera IDs to their display names.

        """
        cameras = self._camera_service.get_all_cameras()
        return {c.id: c.name for c in cameras}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_status(enabled: bool) -> str:
        """Derive a display status string from camera state.

        Without a live runtime health monitor, enabled cameras are
        displayed as ``"online"`` and disabled cameras as
        ``"disabled"``.  A production deployment would integrate
        with the ``CameraHealthMonitor`` for real status.

        Args:
            enabled: Whether the camera is enabled for detection.

        Returns:
            A status string: ``"online"`` or ``"disabled"``.

        """
        return "online" if enabled else "disabled"

    @staticmethod
    def _detection_to_summary(
        model: DetectionModel,
        camera_names: dict[int, str],
    ) -> DetectionSummaryDTO:
        """Convert a ``DetectionModel`` ORM instance to a ``DetectionSummaryDTO``.

        Args:
            model: The ORM model instance.
            camera_names: Lookup map for resolving camera names.

        Returns:
            A ``DetectionSummaryDTO`` suitable for UI display.

        """
        return DetectionSummaryDTO(
            id=model.id,
            camera_id=model.camera_id,
            camera_name=camera_names.get(model.camera_id, f"Camera #{model.camera_id}"),
            plate_text=model.plate_number or "",
            confidence=model.confidence,
            snapshot_path=model.image_path or "",
            video_path=model.video_path or "",
            webhook_status=model.webhook_status,
            detected_at=model.detected_at,
        )

    def __repr__(self) -> str:
        return "<DashboardService>"

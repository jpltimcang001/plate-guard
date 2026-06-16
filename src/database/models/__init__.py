"""SQLAlchemy ORM models for the Plate Guard database schema.

Import order matters to avoid circular dependencies:

1. ``camera_model`` (no FK dependencies)
2. ``zone_model``       (FK → camera)
3. ``webhook_model``    (FK → camera)
4. ``detection_model``  (FK → camera)
"""

from src.database.models.camera_model import CameraModel
from src.database.models.detection_model import DetectionModel
from src.database.models.webhook_model import WebhookModel
from src.database.models.zone_model import ZoneModel

__all__ = [
    "CameraModel",
    "ZoneModel",
    "WebhookModel",
    "DetectionModel",
]

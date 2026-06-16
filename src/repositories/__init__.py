"""Repository implementations for the Plate Guard domain.

Repositories follow the Repository Pattern and abstract database
access behind interfaces defined in the domain layer.
"""

from src.repositories.camera_repository import CameraRepository
from src.repositories.detection_repository import DetectionRepository
from src.repositories.webhook_repository import WebhookRepository
from src.repositories.zone_repository import ZoneRepository

__all__ = [
    "CameraRepository",
    "ZoneRepository",
    "WebhookRepository",
    "DetectionRepository",
]

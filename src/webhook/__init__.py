"""Webhook engine — HTTP notification delivery for plate detection events.

Components
----------
- ``WebhookPayload`` — Domain entity representing data sent in a webhook.
- ``WebhookResult`` — Domain entity representing the outcome of a delivery.
- ``WebhookClient`` — Low-level HTTP client with auth, retry, and file upload.
- ``WebhookService`` — High-level orchestrator that loads configurations,
  builds payloads, dispatches via the client, and records results.
- ``WebhookError`` — Exception raised on unrecoverable delivery failures.
"""

from src.webhook.webhook_client import WebhookClient, WebhookError
from src.webhook.webhook_payload import WebhookPayload, WebhookResult
from src.webhook.webhook_service import WebhookService

__all__ = [
    "WebhookClient",
    "WebhookError",
    "WebhookPayload",
    "WebhookResult",
    "WebhookService",
]

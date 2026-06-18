"""Regression test suite entry point.

This module is automatically picked up by pytest and runs all
unit and integration tests.  It exists as a convenience marker
for CI/CD pipelines that need a single entry point.

Usage:
    python -m pytest tests/test_regression_suite.py -v
"""

from __future__ import annotations

# ------------------------------------------------------------------
# Import test modules so they are discovered by pytest
# Even though pytest auto-discovers tests via ``tests/``,
# this module acts as a documented regression suite entry.
# ------------------------------------------------------------------

# (No imports needed — pytest discovery handles everything.)

# ------------------------------------------------------------------
# Regression checklist (for documentation purposes only)
# ------------------------------------------------------------------
#
# These modules are expected to be present for a complete regression:
#
# Unit tests:
#   tests/unit/test_camera_entity.py
#   tests/unit/test_camera_service.py
#   tests/unit/test_zone_entity.py
#   tests/unit/test_zone_service.py
#   tests/unit/test_plate_detector.py
#   tests/unit/test_detection_result.py
#   tests/unit/test_zone_validator.py
#   tests/unit/test_tracker.py
#   tests/unit/test_duplicate_filter.py
#   tests/unit/test_pipeline.py
#   tests/unit/test_ocr_service.py
#   tests/unit/test_webhook_service.py
#   tests/unit/test_event_recorder.py
#   tests/unit/test_streaming.py
#   tests/unit/test_dashboard_service.py
#   tests/unit/test_exception_handler.py
#   tests/unit/test_shutdown_manager.py
#   tests/unit/test_auto_start.py
#   tests/unit/test_camera_health_monitor.py
#   tests/unit/test_memory_monitor.py
#   tests/unit/test_evidence_retention.py
#   tests/unit/test_dashboard_widget.py
#
# Integration tests:
#   tests/integration/test_camera_repository.py
#   tests/integration/test_zone_repository.py
#   tests/integration/test_detection_repository.py
#   tests/integration/test_webhook_repository.py
#   tests/integration/test_dashboard_service.py
#   tests/integration/test_zone_service.py
#   tests/integration/test_event_recorder.py
#   tests/integration/test_evidence_retention.py
#
# Performance / stress tests:
#   tests/performance/test_16_camera_stress.py
#
# This file itself adds no additional tests.

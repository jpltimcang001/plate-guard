"""Unit-test-specific fixtures for the camera module."""

from __future__ import annotations

from typing import Any

import pytest

from src.detection.usb_enumerator import UsbEnumerator
from src.domain.services.i_camera_service import UsbDeviceInfo


class MockUsbEnumerator:
    """Mock USB enumerator that returns a pre-configured device list."""

    def __init__(self, devices: list[UsbDeviceInfo] | None = None) -> None:
        self._devices = devices or [
            UsbDeviceInfo(index=0, name="Mock Camera 1", hardware_id="USB\\VID_1234"),
            UsbDeviceInfo(index=1, name="Mock Camera 2", hardware_id="USB\\VID_5678"),
        ]

    def list_devices(self) -> list[UsbDeviceInfo]:
        return self._devices

    def device_exists(self, index: int) -> bool:
        return any(d.index == index for d in self._devices)


@pytest.fixture
def mock_usb_enumerator() -> MockUsbEnumerator:
    """Return a mock USB enumerator with two fake devices."""
    return MockUsbEnumerator()


@pytest.fixture
def empty_usb_enumerator() -> MockUsbEnumerator:
    """Return a mock USB enumerator with no devices."""
    return MockUsbEnumerator(devices=[])

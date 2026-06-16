"""Unit tests for the cooldown-based DuplicateFilter.

Tests cover:
- ``is_duplicate`` with cooldown (same text within window)
- ``record`` separate from check
- ``check_and_record`` combined operation
- Clear (single, all) semantics
- Edge cases: empty text, zero cooldown, rapid repeated calls
"""

from __future__ import annotations

import time

import pytest

from src.detection.duplicate_filter import DuplicateFilter


# ======================================================================
# DuplicateFilter initialisation
# ======================================================================


class TestDuplicateFilterInit:
    """Tests for constructor validation."""

    def test_default_cooldown(self) -> None:
        df = DuplicateFilter()
        assert df.cooldown_seconds == 5.0

    def test_custom_cooldown(self) -> None:
        df = DuplicateFilter(cooldown_seconds=10.0)
        assert df.cooldown_seconds == 10.0

    def test_zero_cooldown(self) -> None:
        """Zero cooldown means every call is a new event."""
        df = DuplicateFilter(cooldown_seconds=0.0)
        assert df.is_duplicate("ABC") is False

    def test_negative_cooldown_raises(self) -> None:
        with pytest.raises(ValueError, match="cooldown_seconds"):
            DuplicateFilter(cooldown_seconds=-1.0)


# ======================================================================
# is_duplicate
# ======================================================================


class TestIsDuplicate:
    """Tests for the read-only duplicate check."""

    def test_never_seen_is_not_duplicate(self) -> None:
        df = DuplicateFilter()
        assert df.is_duplicate("ABC-123") is False

    def test_recently_recorded_is_duplicate(self) -> None:
        df = DuplicateFilter()
        df.record("ABC-123")
        assert df.is_duplicate("ABC-123") is True

    def test_different_text_not_duplicate(self) -> None:
        df = DuplicateFilter()
        df.record("ABC-123")
        assert df.is_duplicate("XYZ-999") is False

    def test_empty_string(self) -> None:
        df = DuplicateFilter()
        assert df.is_duplicate("") is False
        df.record("")
        # Empty strings are never considered duplicates (design choice)
        assert df.is_duplicate("") is False

    def test_case_sensitivity(self) -> None:
        df = DuplicateFilter()
        df.record("abc")
        assert df.is_duplicate("ABC") is False
        assert df.is_duplicate("abc") is True


# ======================================================================
# record
# ======================================================================


class TestRecord:
    """Tests for the record() method."""

    def test_recording_fresh_text(self) -> None:
        df = DuplicateFilter()
        df.record("ABC-123")
        assert df.is_duplicate("ABC-123") is True

    def test_recording_refreshes_timestamp(self) -> None:
        """Re-recording the same text resets the cooldown window."""
        df = DuplicateFilter(cooldown_seconds=0.5)

        # Record, wait, record again, check immediately — should be duplicate
        df.record("ABC-123")
        time.sleep(0.05)
        df.record("ABC-123")  # refresh
        # Since we just refreshed, it should be duplicate
        assert df.is_duplicate("ABC-123") is True


# ======================================================================
# check_and_record
# ======================================================================


class TestCheckAndRecord:
    """Tests for the combined check-and-record.

    ``check_and_record`` returns ``True`` when the text is **accepted**
    (not a duplicate), and ``False`` when it is suppressed (duplicate).
    """

    def test_first_call_returns_true(self) -> None:
        """First time seeing a plate — accepted."""
        df = DuplicateFilter()
        assert df.check_and_record("ABC-123") is True

    def test_second_call_returns_false(self) -> None:
        """Same plate within cooldown — suppressed."""
        df = DuplicateFilter()
        df.check_and_record("ABC-123")
        assert df.check_and_record("ABC-123") is False

    def test_third_call_before_cooldown_still_false(self) -> None:
        """Repeated calls within cooldown continue to suppress."""
        df = DuplicateFilter(cooldown_seconds=10.0)
        df.check_and_record("ABC-123")
        assert df.check_and_record("ABC-123") is False
        assert df.check_and_record("ABC-123") is False

    def test_different_text_after_first(self) -> None:
        """Different plate text is accepted even after recording another."""
        df = DuplicateFilter()
        df.check_and_record("ABC-123")
        assert df.check_and_record("XYZ-999") is True  # different — accepted


# ======================================================================
# Clear
# ======================================================================


class TestClear:
    """Tests for resetting the filter state."""

    def test_clear_single_text(self) -> None:
        df = DuplicateFilter()
        df.record("ABC-123")
        df.record("XYZ-999")
        df.clear(plate_text="ABC-123")
        assert df.is_duplicate("ABC-123") is False
        assert df.is_duplicate("XYZ-999") is True

    def test_clear_all(self) -> None:
        df = DuplicateFilter()
        df.record("ABC-123")
        df.record("XYZ-999")
        df.clear()
        assert df.is_duplicate("ABC-123") is False
        assert df.is_duplicate("XYZ-999") is False

    def test_clear_nonexistent_text_does_nothing(self) -> None:
        df = DuplicateFilter()
        df.record("ABC-123")
        df.clear(plate_text="NONEXISTENT")
        assert df.is_duplicate("ABC-123") is True

    def test_clear_empty_text(self) -> None:
        df = DuplicateFilter()
        df.record("")
        df.clear(plate_text="")
        assert df.is_duplicate("") is False


# ======================================================================
# Cooldown expiration
# ======================================================================


class TestCooldownExpiration:
    """Verify that entries expire after the cooldown period."""

    def test_expires_after_cooldown(self) -> None:
        df = DuplicateFilter(cooldown_seconds=0.1)
        df.record("ABC-123")
        assert df.is_duplicate("ABC-123") is True
        time.sleep(0.15)
        assert df.is_duplicate("ABC-123") is False

    def test_check_and_record_resets_cooldown(self) -> None:
        """Calling ``record`` after a suppression refreshes the cooldown."""
        df = DuplicateFilter(cooldown_seconds=0.3)
        assert df.check_and_record("ABC-123") is True  # first — accepted
        time.sleep(0.2)

        # Still within cooldown from first record → suppressed
        # Note: check_and_record does NOT refresh timestamp on suppression
        assert df.check_and_record("ABC-123") is False  # suppressed

        time.sleep(0.15)  # total 0.35s from first record
        # Cooldown expired from the original record (0.35 > 0.3)
        # → no longer a duplicate (suppress call at 0.2s did not refresh)
        assert df.is_duplicate("ABC-123") is False

        # Now record explicitly to refresh
        df.record("ABC-123")
        assert df.is_duplicate("ABC-123") is True  # within cooldown again


# ======================================================================
# Edge cases
# ======================================================================


class TestEdgeCases:
    """Additional edge-case scenarios."""

    def test_many_unique_plates(self) -> None:
        """Large numbers of unique plates should all be accepted."""
        df = DuplicateFilter(cooldown_seconds=5.0)
        for i in range(1000):
            plate = f"PLATE-{i:04d}"
            assert df.check_and_record(plate) is True

    def test_whitespace_sensitivity(self) -> None:
        """Whitespace is not stripped — 'ABC' vs 'ABC ' are different."""
        df = DuplicateFilter()
        df.record("ABC")
        assert df.is_duplicate("ABC ") is False

    def test_regression_empty_after_expiry(self) -> None:
        """After all entries expire, filter should have an empty clean state."""
        df = DuplicateFilter(cooldown_seconds=0.05)
        df.record("A")
        df.record("B")
        time.sleep(0.1)
        assert df.is_duplicate("A") is False
        assert df.is_duplicate("B") is False
        assert df.check_and_record("C") is True  # fresh start — accepted

    def test_clear_does_not_affect_other_state(self) -> None:
        """Clearing one text should not change other cooldowns."""
        df = DuplicateFilter()
        df.record("A")
        df.record("B")
        df.clear(plate_text="A")
        assert df.is_duplicate("B") is True

    def test_repr(self) -> None:
        df = DuplicateFilter(cooldown_seconds=3.0)
        df.record("ABC")
        rep = repr(df)
        assert "DuplicateFilter" in rep
        assert "cooldown=3.0" in rep
        assert "tracked=1" in rep

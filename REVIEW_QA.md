# QA Review

**Reviewer:** qa-engineer  
**Date:** 2026-06-15  
**Scope:** Test coverage, test quality, edge cases, fixtures, assertions

---

## Summary

The test suite is comprehensive with 52 tests across 3 test files. Test organization is excellent with class-based grouping. The mock repository enables fast, isolated unit tests. There are several gaps in coverage and test robustness that should be addressed.

---

## Test Inventory

| Test File | Type | Test Classes | Tests | Status |
|-----------|------|-------------|-------|--------|
| `test_camera_entity.py` | Unit (domain) | 5 | 16 | ✅ Covers creation, validation, behaviour, equality |
| `test_camera_service.py` | Unit (service) | 5 | 20 | ✅ Covers CRUD, enable/disable, queries, USB enumeration |
| `test_camera_repository.py` | Integration (DB) | 5 | 16 | ✅ Covers add, get, update, delete, count |
| **Total** | | **15** | **52** | |

---

## Strengths

### 1. Test Organization
- Class-based grouping per operation (`TestAddCamera`, `TestEditCamera`, etc.) makes it easy to find related tests.
- Clear test method names and docstrings explaining the scenario.
- Shared fixtures in `conftest.py` reduce duplication.

### 2. Mock Strategy
- `MockCameraRepository` is a faithful in-memory implementation of `ICameraRepository`.
- `MockUsbEnumerator` allows testing USB validation without actual hardware.
- Service tests have zero infrastructure dependencies.

### 3. Edge Case Coverage (good)
- ✅ Empty name
- ✅ Whitespace-only name (entity test)
- ✅ Empty RTSP URL
- ✅ Missing USB index
- ✅ Negative USB index
- ✅ Confidence threshold < 0 and > 1
- ✅ Duplicate name detection
- ✅ Non-existent camera (all operations)
- ✅ No USB enumerator configured

---

## Issues & Recommendations

### QA-01: No test for deleting a camera that has associated zones/webhooks/detections

**Severity:** High  
**File:** Missing  
**Problem:** The `delete` operation has a cascade delete at the DB level, but there's no test verifying that deleting a camera with associated records works correctly. The integration tests only test with standalone cameras.

**Recommendation:** Add an integration test:
```python
def test_delete_camera_cascades_to_zones(self, camera_repo, zone_repo):
    camera = camera_repo.add(Camera.create_rtsp(...))
    zone = zone_repo.add(Zone(camera_id=camera.id, name="Z1", polygon_json=...))
    camera_repo.delete(camera.id)
    assert zone_repo.get_by_id(zone.id) is None
```

### QA-02: No test for editing a camera from RTSP to USB (or vice versa)

**Severity:** Medium  
**File:** Missing  
**Problem:** The edit operation can change fields that are inconsistent with the camera type (see CODE-03). There are no tests covering this scenario.

**Recommendation:** Add tests:
- Edit an RTSP camera with `usb_index` set → should raise validation error.
- Edit a USB camera with `rtsp_url` set → should raise validation error.
- Verify that editing a camera's name only doesn't affect other fields.

### QA-03: Database tests don't verify isolation between tests

**Severity:** Medium  
**File:** `tests/integration/test_camera_repository.py`  
**Problem:** The integration tests share a `session_manager` but don't explicitly wrap each test in a transaction that rolls back. The `db_session` fixture is defined but never used in the integration tests — the `camera_repo` fixture uses `session_manager` directly.

```python
# conftest.py has a db_session fixture, but integration tests don't use it
@pytest.fixture
def camera_repo(session_manager) -> CameraRepository:
    return CameraRepository(session_manager)
```

**Recommendation:** Either:
- Use the `db_session` fixture in each test to provide transaction isolation.
- Or add a `@pytest.fixture(autouse=True)` that cleans up all tables between tests.

### QA-04: `test_add_duplicate_name_raises_integrity_error` catches generic `Exception`

**Severity:** Medium  
**File:** `tests/integration/test_camera_repository.py` lines 45-54  
**Problem:** The test catches the broad `Exception` class:
```python
with pytest.raises(Exception):  # SQLAlchemy integrity error
    camera_repo.add(c2)
```

This could mask unrelated errors (e.g., connection issues, type errors). SQLAlchemy raises a specific `IntegrityError` (a subclass of `SQLAlchemyError`).

**Recommendation:** Catch a more specific exception:
```python
from sqlalchemy.exc import IntegrityError
with pytest.raises(IntegrityError):
    camera_repo.add(c2)
```

### QA-05: `test_add_usb_camera_invalid_index_with_enumerator` imports inside the test

**Severity:** Low  
**File:** `tests/unit/test_camera_service.py` line 150  
**Problem:** The import is inside the test method rather than at the top of the file:
```python
def test_add_usb_camera_invalid_index_with_enumerator(self, ...):
    from src.application.exceptions.camera_errors import CameraConnectionError
    ...
```

All other tests use top-level imports.

**Recommendation:** Move the import to the top of the file.

### QA-06: No tests for `CameraService.get_camera` with a valid camera that was just created and then verified

**Severity:** Low  
**File:** Missing  
**Problem:** `test_get_camera_by_id` creates a camera and then fetches it, but doesn't verify that the fetched DTO matches the original in all fields (particularly `confidence_threshold` and `rtsp_url`).

**Recommendation:** Add field-by-field comparison:
```python
fetched = camera_service.get_camera(created.id)
assert fetched.name == created.name
assert fetched.camera_type == created.camera_type  # DTO stores as "rtsp"
assert fetched.confidence_threshold == created.confidence_threshold
```

### QA-07: No negative-edge tests for USB enumerator

**Severity:** Low  
**File:** Missing  
**Problem:** The `MockUsbEnumerator` is always configured with the same two devices. There are no tests for:
- Empty USB device list.
- USB enumerator that raises an exception.
- USB device index 0 being the only available device.

### QA-08: No test for the `sample_cameras` fixture

**Severity:** Low  
**File:** `tests/conftest.py` lines 91-109  
**Problem:** The `sample_cameras` fixture persists test data but is never used by any test. It was likely intended for query tests.

**Recommendation:** Either use the fixture in tests or remove it to avoid dead code.

### QA-09: Missing `pytest.mark.dependency` or test ordering

**Severity:** Low  
**Files:** All test files  
**Problem:** Tests within classes may have implicit ordering dependencies (e.g., `test_enable_camera` followed by `test_disable_camera`). While they currently don't depend on each other (each creates its own data), this isn't enforced.

**Recommendation:** No action needed currently, but as the suite grows, consider using `pytest-dependency` or ensuring each test is truly independent.

---

## Coverage Analysis

### Code Coverage (estimated)

| Module | Lines | Tested | Coverage |
|--------|-------|--------|----------|
| `domain/entities/camera.py` | 160 | ✅ Yes | ~95% |
| `domain/value_objects/camera_type.py` | 12 | ✅ Yes | ~100% |
| `domain/repositories/i_camera_repository.py` | 153 | ⚠️ Protocol | N/A (no logic) |
| `domain/services/i_camera_service.py` | 171 | ⚠️ Protocol | N/A (no logic) |
| `application/dto/camera_dto.py` | 43 | ⚠️ Partial | ~60% (no DTO-specific tests) |
| `application/exceptions/camera_errors.py` | 34 | ✅ Yes | ~80% |
| `services/camera_service.py` | 321 | ✅ Yes | ~90% |
| `repositories/camera_repository.py` | 181 | ✅ Yes | ~90% (via integration) |
| `detection/usb_enumerator.py` | 121 | ⚠️ Partial | ~30% (no real hardware tests) |

### Gap Analysis

| Gap | Severity | Suggestion |
|-----|----------|------------|
| No cascade delete test | High | Add integration test with zones/webhooks |
| No type-change validation test | Medium | Test editing RTSP cam with USB fields |
| Integration tests don't roll back | Medium | Use `db_session` fixture |
| Generic Exception catch | Medium | Use `IntegrityError` instead |
| `sample_cameras` fixture unused | Low | Remove or use in tests |
| No DTO serialization/deserialization tests | Low | Add tests if DTOs become more complex |
| Import inside test method | Low | Move to top of file |

---

## Test Execution Readiness

The test suite should pass with the following prerequisites:
1. `pytest` installed
2. `pytest` discovers tests in `tests/`
3. SQLAlchemy models import correctly (no circular imports)
4. No OpenCV dependency needed for unit tests (mock enumerator used)
5. Integration tests use in-memory SQLite (no real DB needed)

**Estimated pass rate:** ~95% (some edge cases around type mismatches may cause issues with `mypy` but `pytest` should pass).

# Code Review

**Reviewer:** code-reviewer  
**Date:** 2026-06-15  
**Scope:** Code style, type hints, error handling, logging, patterns, edge cases

---

## Summary

The codebase is well-structured with consistent style, good docstrings, and proper type hints. Several issues around type safety, error handling completeness, and potential runtime edge cases need addressing.

---

## Strengths

### 1. Code Style & Documentation
- Consistent docstring style (Google/NumPy-inspired) throughout.
- `__repr__` methods on all entities and models.
- Class-based test organization for readability.
- `from __future__ import annotations` in all files.
- Loguru for structured logging with proper log levels (trace/debug/info).

### 2. Type Hints
- Full coverage of function signatures with type hints.
- Generics used correctly in `BaseRepository[T]`.
- `Optional[str]` vs `str | None` usage is consistent (though mixed — note: line 12 of `camera.py` imports `Optional` but the code uses `str | None`).

### 3. Error Handling
- Custom exception hierarchy (`CameraNotFoundError`, `DuplicateNameError`, `CameraConnectionError`).
- Domain validation raises `ValueError` with descriptive messages.
- Repository methods return `bool` or `None` for not-found cases.

---

## Issues & Recommendations

### CODE-01: `Camera` entity's `id` field uses `field(default=None, compare=False)` — comparison semantics are fragile

**Severity:** Medium  
**File:** `src/domain/entities/camera.py` line 24  
**Problem:** `compare=False` means two `Camera` instances with the same attribute values but different `id` are considered equal. The value `compare=False` makes `id` excluded from `__eq__`. This means two transient (unsaved) cameras with different names could accidentally compare as equal if all other fields match.

```python
id: int | None = field(default=None, compare=False)
```

**Recommendation:** Consider whether identity-based equality is more appropriate:
```python
def __eq__(self, other):
    if not isinstance(other, Camera):
        return NotImplemented
    if self.id is not None and other.id is not None:
        return self.id == other.id
    return self is other  # reference equality for transient entities
```

### CODE-02: `CameraService._to_dto` maps `None` id to `0` — sentinel value confusion

**Severity:** Medium  
**File:** `src/services/camera_service.py` line 312  
**Problem:** When converting a domain entity with `id=None` to a DTO, it maps to `0`. This is problematic because:
- `0` is a valid auto-increment ID in some databases (though rare for SQLite).
- Downstream code cannot distinguish between "unsaved" (0) and "saved with id=0" (unlikely but possible).

```python
id=camera.id if camera.id is not None else 0,
```

**Recommendation:** Keep `id` as `int | None` in the DTO. The presentation layer should handle `None` (display "N/A" or new badge).

### CODE-03: `edit_camera` allows changing camera type indirectly via field values

**Severity:** Medium  
**File:** `src/services/camera_service.py` lines 128-181  
**Problem:** The `edit_camera` method accepts `rtsp_url` and `usb_index` but doesn't validate consistency with the camera's current type. For example:
- Calling `edit_camera(camera_id, rtsp_url="rtsp://...")` on a USB camera would set the URL without changing the type.
- Calling `edit_camera(camera_id, usb_index=2)` on an RTSP camera would set the index without changing the type.
- The `validate()` call would catch this (e.g., RTSP cam with `usb_index` set but no `rtsp_url`), but the error message would be confusing.

**Recommendation:** Either:
- Explicitly check type consistency in `edit_camera`.
- Or make type changes require explicit `camera_type` parameter.
- At minimum, clear the contradictory field: setting `rtsp_url` on a USB cam should clear `usb_index` and vice versa.

### CODE-04: `UsbEnumerator` uses `logging.getLogger` while the rest of the project uses Loguru

**Severity:** Low  
**File:** `src/detection/usb_enumerator.py` line 17  
**Problem:** Inconsistent logging approach — the rest of the codebase uses `from loguru import logger`. This file uses the standard library `logging` module.

**Recommendation:** Switch to Loguru for consistency:
```python
from loguru import logger
```

### CODE-05: `CameraModel` uses `Integer` for boolean `enabled` field

**Severity:** Low  
**File:** `src/database/models/camera_model.py` line 32  
**Problem:** `Mapped[bool] = mapped_column(Integer, default=0, nullable=False)` — While SQLite doesn't have a native BOOLEAN type, SQLAlchemy's `Boolean` type handles this automatically (stores as 0/1). Using `Boolean` is more expressive.

```python
from sqlalchemy import Boolean
enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

**Recommendation:** Use `Boolean` type so the ORM handles Python `True`/`False` ↔ integer conversion.

### CODE-06: `delete_camera_with_dependencies` in CameraRepository just calls `delete()` — misleading name

**Severity:** Low  
**File:** `src/repositories/camera_repository.py` line 169-181  
**Problem:** The method `delete_camera_with_dependencies` simply delegates to `self.delete(camera_id)`. The cascade delete is handled at the DB level via `ON DELETE CASCADE`, so the name is accurate in effect but misleading in implementation — it suggests there's application-level logic for dependency deletion.

**Recommendation:** Either remove the method (since `delete()` already handles it via cascade) or document that cascade is DB-managed.

### CODE-07: `MockCameraRepository.update()` mutates the input entity

**Severity:** Low  
**File:** `tests/conftest.py` lines 151-154  
**Problem:** The mock's `update()` method mutates the passed-in camera by assigning `camera.id` in `add()`. This is fine for testing but differs from the real `CameraRepository.update()` which uses `session.merge()` and returns a (potentially) different object. If tests rely on reference equality, this could cause confusion.

**Recommendation:** Add a comment to the mock noting this behavioral difference, or make the mock return a copy.

### CODE-08: No input validation for `edit_camera` on RTSP URL format

**Severity:** Low  
**File:** `src/services/camera_service.py` line 167  
**Problem:** When updating `rtsp_url`, there's no validation that the URL is a valid RTSP URL (e.g., starts with `rtsp://`). The domain entity's `validate()` only checks for non-empty string.

```python
if rtsp_url is not None:
    camera.rtsp_url = rtsp_url if rtsp_url else None
```

**Recommendation:** Add URL format validation in the Camera entity's `validate()` method or in the service layer.

### CODE-09: `enabled` field default inconsistency

**Severity:** Low  
**File:** `src/domain/entities/camera.py` line 39  
**Problem:** The domain entity defaults `enabled = False`, but the ORM model defaults `enabled = 0`. These are consistent in meaning, but it's worth verifying that the ORM default matches the domain default in all migration scenarios.

**Recommendation:** No action needed — they are consistent. Just flagging for awareness.

---

## Type Safety Verdict

```
mypy --strict readiness: ⚠️  Almost ready
```

Issues to fix:
1. Repository returns `CameraModel` where `Camera` is expected (see ARCH-01).
2. Service returns `CameraDTO` where `Camera` is declared (see ARCH-02).
3. Mixed use of `Optional[str]` and `str | None` in `camera.py` (imports `Optional` but uses pipe syntax).

These will all be caught by `mypy --strict`.

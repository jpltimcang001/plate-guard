# Database Review

**Reviewer:** database-engineer  
**Date:** 2026-06-15  
**Scope:** ORM models, repository pattern, engine configuration, migrations, session management

---

## Summary

The database layer is well-structured with proper SQLAlchemy 2.x Mapped syntax, WAL mode configuration, and session management. The ERD schema is faithfully implemented. Some areas around transaction safety and migration readiness need attention.

---

## Strengths

### 1. Model Definitions
- SQLAlchemy 2.x Mapped-column syntax is used consistently.
- `server_default=func.now()` for timestamps is correct.
- Unique constraint on `CameraModel.name` with index is appropriate.
- `ondelete="CASCADE"` foreign keys with `passive_deletes=True` for referential integrity.
- Nullable/required fields match the ERD specification.

### 2. Engine Configuration
- WAL journal mode, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000` are all appropriate for a multi-threaded desktop application.
- 8 MB cache (`cache_size=-8000`) and `temp_store=MEMORY` are good defaults.

### 3. Session Management
- `SessionManager` provides both scoped and unscoped session access.
- Context managers handle commit/rollback correctly.
- `expire_on_commit=False` avoids premature expiration.

### 4. Migration Structure
- Alembic configuration is present with autogenerate support.
- `env.py` correctly imports all models for metadata discovery.

---

## Issues & Recommendations

### DB-01: Repository `update()` uses `session.merge()` which is problematic for detached entities

**Severity:** High  
**File:** `src/repositories/base.py` line 126  
**Problem:** `session.merge()` issues a SELECT before every UPDATE to check for existing rows in the identity map. For detached entities (which is what the domain entities are — they're not SQLAlchemy models), merge can behave unpredictably and can also accidentally persist related objects.

```python
def update(self, entity: T) -> T:
    merged = session.merge(entity)  # Problematic for detached entities
```

**Recommendation:** Since the repositories work with SQLAlchemy ORM models (not domain entities — see ARCH-01), the `update()` method should either:
- Accept the entity ID + a dict of values and perform a direct UPDATE.
- Or retrieve the existing object via `get()`, set attributes, and flush.
- Avoid `merge()` unless working with truly detached instances across sessions.

### DB-02: `BaseRepository._session()` uses scoped session, but `CameraRepository` inherits this

**Severity:** Medium  
**File:** `src/repositories/base.py`  
**Problem:** All repository methods use `self._session()` which returns the thread-local scoped session. This means:
- The session is shared across all operations within the same thread.
- There is no explicit transaction boundary — `flush()` is used but `commit()` is never called by the repository.
- The caller (service layer) has no control over transaction boundaries.

**Recommendation:** One of:
- Have repositories accept an explicit `Session` parameter (session-per-operation).
- Or have the service layer wrap operations in a transaction using `SessionManager.session()` context manager.
- Document that the caller is responsible for committing.

### DB-03: `CameraRepository` methods don't commit — service layer doesn't commit either

**Severity:** High  
**File:** `src/repositories/camera_repository.py` and `src/services/camera_service.py`  
**Problem:** Looking at the flow:
1. `CameraService.add_camera()` calls `self._repo.add(camera)` which calls `session.add()` + `session.flush()` + `session.refresh()`.
2. Neither the repository nor the service calls `session.commit()`.
3. The scoped session is never committed in normal operation.

**Recommendation:** The service layer should wrap operations in a transaction:
```python
from src.database.session import SessionManager

class CameraService:
    def __init__(self, repo, session_manager):
        self._repo = repo
        self._session_manager = session_manager
    
    def add_camera(self, ...):
        with self._session_manager.session() as session:
            # use session explicitly
            ...
```
Or, alternatively, add a `commit()` call in the service after the repository operation succeeds, and `rollback()` on failure.

### DB-04: No validation for `usb_index` uniqueness

**Severity:** Low  
**File:** `src/database/models/camera_model.py`  
**Problem:** The `cameras` table has no unique constraint on `usb_index`. Two cameras could theoretically be configured with the same USB index.

**Recommendation:** Either add a partial unique constraint (though SQLite doesn't support partial indexes easily) or enforce this at the service layer.

### DB-05: Migration initial state not tracked

**Severity:** Medium  
**File:** `src/database/migrations/versions/`  
**Problem:** The `versions/` directory contains only a `.gitkeep`. There is no initial migration that creates the schema. On a fresh database, `init_db()` (via `Base.metadata.create_all()`) creates tables directly, bypassing Alembic's version tracking.

**Recommendation:** Generate an initial migration with `alembic revision --autogenerate -m "initial schema"` so that future migrations have a baseline to diff against. The `init_db()` fallback can remain for development/ease-of-use.

### DB-06: `bulk_delete` doesn't handle empty `entity_ids` consistently

**Severity:** Low  
**File:** `src/repositories/base.py` lines 208-229  
**Problem:** `bulk_delete` correctly returns 0 for empty input, but `bulk_insert` returns `[]` for empty input. This consistency is fine, but `bulk_delete` logs no trace for empty input while `bulk_insert` also logs nothing. Not a bug, but an inconsistency in observability.

**Recommendation:** Add a trace log to `bulk_delete` early return for consistency.

### DB-07: `error_message` parameter in `DetectionRepository.update_webhook_status()` is unused

**Severity:** Low  
**File:** `src/repositories/detection_repository.py` lines 44-64  
**Problem:** The `error_message` parameter is accepted but never stored (just a `pass` comment). If error details should be persisted, add a column; if not, remove the parameter.

**Recommendation:** Either add an `error_message` column to the `detections` table or remove the parameter.

---

## Database Schema Compliance

| ERD Table | Model File | Status | Notes |
|-----------|-----------|--------|-------|
| cameras | `camera_model.py` | ✅ | Matches ERD + timestamps |
| zones | `zone_model.py` | ✅ | Matches ERD + timestamps |
| webhooks | `webhook_model.py` | ✅ | Matches ERD + timestamps |
| detections | `detection_model.py` | ✅ | Matches ERD + timestamps |
| FK constraints | All models | ✅ | CASCADE deletes configured |
| Indexes | camera.name, camera.enabled, zone.camera_id, webhook.camera_id, detection.camera_id, detection.plate_number, detection.detected_at | ✅ | Good coverage |

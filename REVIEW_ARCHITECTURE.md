# Architecture Review

**Reviewer:** architect  
**Date:** 2026-06-15  
**Scope:** Domain layer, application layer, service layer, separation of concerns, dependency inversion

---

## Summary

The Camera Management Module follows Clean Architecture principles with clear separation between domain, application, and infrastructure layers. Dependency inversion is achieved through Protocol-based interfaces. Overall the architecture is sound with a few areas for improvement.

---

## Strengths

### 1. Clean Domain-Infrastructure Separation
- The `Camera` entity in `src/domain/entities/camera.py` is a pure dataclass with zero framework dependencies (no SQLAlchemy, no Qt, no OpenCV).
- The `CameraModel` in `src/database/models/camera_model.py` is a separate ORM class — the domain is not polluted by persistence concerns.
- This separation is correctly maintained throughout.

### 2. Protocol-Based Dependency Inversion
- `ICameraRepository` in `src/domain/repositories/i_camera_repository.py` is a `Protocol` class defining the contract.
- `CameraService` depends on `ICameraRepository` (the abstraction), not on `CameraRepository` (the implementation).
- The service receives its dependencies via constructor injection.

### 3. Service Interface
- `ICameraService` in `src/domain/services/i_camera_service.py` provides a formal contract that the service implementation must satisfy.

### 4. Aggregate Root Awareness
- `Camera` is correctly treated as the aggregate root with ownership of zones and webhooks.
- Cascade delete is configured at the ORM level.

---

## Issues & Recommendations

### ARCH-01: Repository interface returns domain entity but implementation returns ORM model — type mismatch

**Severity:** High  
**File:** `src/repositories/camera_repository.py`  
**Problem:** The `ICameraRepository` protocol declares return types as `Camera` (domain entity), but the `CameraRepository` implementation returns `CameraModel` (ORM model). These are different types. Since Python Protocols use structural subtyping, this won't cause a runtime error but it breaks type safety — `mypy --strict` will flag this.

```python
# Protocol says:
def get_by_id(self, camera_id: int) -> Camera | None: ...

# Implementation returns:
def get_by_id(self, camera_id: int) -> CameraModel | None: ...
```

**Recommendation:** Add a mapper/adapter between `CameraModel` and `Camera`. The repository implementation should:
1. Query `CameraModel` from the database
2. Map it to a `Camera` domain entity
3. Return the domain entity

Similarly, `add()` should accept a `Camera` domain entity and convert it to a `CameraModel` for persistence.

### ARCH-02: `CameraService` returns DTOs but service interface declares domain entities

**Severity:** Medium  
**Files:** `src/domain/services/i_camera_service.py` → `src/services/camera_service.py`  
**Problem:** The `ICameraService` Protocol declares return type `Camera` (domain entity), but the `CameraService` implementation actually returns `CameraDTO`. The Protocol's method signatures are:

```python
def add_camera(...) -> Camera: ...   # Protocol says Camera
# But actual implementation returns:
def add_camera(...) -> CameraDTO:    # Returns CameraDTO
```

**Recommendation:** Either update the Protocol to return `CameraDTO` (which may introduce a domain → application dependency), or change the service to return domain entities and let the presentation layer convert to DTOs. The cleaner approach is to return `Camera` from the service and convert to DTOs in the presentation layer.

### ARCH-03: `UsbDeviceInfo` is defined in the domain service interface but is an infrastructure concern

**Severity:** Low  
**File:** `src/domain/services/i_camera_service.py`  
**Problem:** `UsbDeviceInfo` is a simple data holder that represents USB device detection results. It's defined in the domain service interface, but USB enumeration is purely an infrastructure concern. Domain layers should not know about USB devices.

**Recommendation:** Move `UsbDeviceInfo` to the infrastructure layer (e.g., `src/detection/usb_enumerator.py`) and have the `ICameraService` protocol return a more generic type, or define the DTO in the application layer.

### ARCH-04: `CameraService` has optional USB enumerator — conditional logic in application service

**Severity:** Low  
**File:** `src/services/camera_service.py`  
**Problem:** The service checks `if self._usb_enumerator is not None` in multiple places, which introduces conditional infrastructure-awareness in the application layer.

**Recommendation:** Use the Null Object pattern — provide a `NullUsbEnumerator` that implements the same interface but returns an empty list. This eliminates the `None` checks and simplifies the service.

---

## Architectural Compliance

| Principle | Status | Notes |
|-----------|--------|-------|
| Single Responsibility | ✅ | Each class has a clear purpose |
| Open/Closed | ✅ | Repos open for extension via inheritance |
| Liskov Substitution | ⚠️ | See ARCH-01: repo returns ORM model not domain entity |
| Interface Segregation | ✅ | `ICameraRepository` has focused methods |
| Dependency Inversion | ⚠️ | See ARCH-01 and ARCH-02 |
| Clean Architecture layers | ✅ | Domain → Application → Infrastructure |
| Repository Pattern | ⚠️ | Implementation leaks ORM types |
| Service Layer | ⚠️ | Returns DTOs instead of domain entities |

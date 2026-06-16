# Risk Assessment

> **Project:** Plate Guard — AI License Plate Recognition Desktop Application
> **Document Version:** 1.0
> **Date:** 2026-06-15

---

## Risk Matrix

| Score | Range | Classification |
|-------|-------|---------------|
| 1–3 | Low | Acceptable, monitor |
| 4–6 | Medium | Requires mitigation plan |
| 7–9 | High | Requires active mitigation and contingency |

### Probability / Impact Matrix

| | Impact: Low | Impact: Med | Impact: High |
|---|:---:|:---:|:---:|
| **Prob: Low** | 1 (Low) | 2 (Low) | 3 (Low) |
| **Prob: Med** | 2 (Low) | 4 (Medium) | 6 (Medium) |
| **Prob: High** | 3 (Low) | 6 (Medium) | 9 (High) |

---

## Identified Risks

### R-001 — YOLOv8 Inference Performance Below Target

- **Category:** Technical
- **Description:** YOLOv8 model may not achieve required inference speed (≥10 FPS) on target hardware, especially with 16 concurrent cameras.
- **Probability:** Medium
- **Impact:** High
- **Risk Score:** 6 (Medium)
- **Mitigation Strategy:**
  - Benchmark YOLOv8 variants (nano, small, medium) early in Sprint 2.
  - Use INT8 quantization or TensorRT if GPU is available.
  - Implement frame skipping/downscaling for low-priority cameras.
- **Contingency Plan:**
  - Fall back to YOLOv8-nano (smallest model) for all cameras.
  - Reduce per-camera FPS from 10 to 5 for non-critical cameras.
  - Move detection to separate GPU-accelerated worker processes.
- **Owner:** CV/ML Engineer

---

### R-002 — PaddleOCR Accuracy Insufficient for Target Plates

- **Category:** Technical
- **Description:** PaddleOCR may produce low recognition accuracy for certain plate formats, fonts, or under poor lighting conditions.
- **Probability:** Medium
- **Impact:** Medium
- **Risk Score:** 4 (Medium)
- **Mitigation Strategy:**
  - Test PaddleOCR against a diverse dataset of target plate formats early.
  - Implement OCR confidence threshold filtering to discard low-quality reads.
  - Evaluate alternative OCR engines (Tesseract, EasyOCR) as fallbacks.
- **Contingency Plan:**
  - Add configurable OCR engine selection in Settings.
  - Fine-tune PaddleOCR on a small dataset of target plates.
  - Implement OCR result aggregation across multiple frames for higher confidence.
- **Owner:** CV/ML Engineer

---

### R-003 — Camera Stream Instability / Frequent Disconnects

- **Category:** Operational
- **Description:** RTSP streams from IP cameras may drop intermittently due to network issues, camera firmware bugs, or bandwidth limitations.
- **Probability:** High
- **Impact:** Medium
- **Risk Score:** 6 (Medium)
- **Mitigation Strategy:**
  - Implement robust auto-reconnect with exponential backoff (R-031).
  - Set TCP transport for RTSP (more reliable than UDP).
  - Add buffer management to handle brief network interruptions.
- **Contingency Plan:**
  - Implement a health-check watchdog that restarts the entire camera pipeline on repeated failures.
  - Log detailed disconnect reasons for network team troubleshooting.
  - Provide manual "Restart Camera" button in UI.
- **Owner:** CV/ML Engineer

---

### R-004 — SQLite Concurrent Write Contention

- **Category:** Technical
- **Description:** With 16 cameras generating detection events simultaneously, SQLite may experience write contention leading to slow inserts or `database is locked` errors.
- **Probability:** Medium
- **Impact:** Medium
- **Risk Score:** 4 (Medium)
- **Mitigation Strategy:**
  - Use WAL (Write-Ahead Log) mode for concurrent reads/writes.
  - Batch detection log inserts (flush every 100ms or 10 events).
  - Use a dedicated write queue with a single writer thread.
- **Contingency Plan:**
  - Fall back to separate detection event queue with batch write on overflow.
  - Consider migrating to PostgreSQL or SQL Server if SQLite proves insufficient.
  - Implement connection retry with backoff for locked errors.
- **Owner:** Backend Engineer

---

### R-005 — Memory Leak in Long-Running 24/7 Operation

- **Category:** Technical
- **Description:** Accumulated frame buffers, undischarged OpenCV resources, or unclosed file handles could cause gradual memory growth over days of continuous operation.
- **Probability:** Medium
- **Impact:** High
- **Risk Score:** 6 (Medium)
- **Mitigation Strategy:**
  - Implement memory profiling in CI (track per-function allocations).
  - Use `gc` module to monitor object counts during soak tests.
  - Enforce strict resource cleanup in context managers (`with` blocks).
- **Contingency Plan:**
  - Add automatic restart of the detection pipeline every 24 hours.
  - Implement a memory watchdog that logs warnings when usage exceeds thresholds.
  - Add a "System Health" panel in UI showing memory/CPU usage.
- **Owner:** Backend Engineer

---

### R-006 — PySide6 UI Freezing During Heavy Processing

- **Category:** Technical
- **Description:** Long-running operations (detection pipeline, evidence saving) on the main thread could cause the UI to become unresponsive.
- **Probability:** High
- **Impact:** Medium
- **Risk Score:** 6 (Medium)
- **Mitigation Strategy:**
  - Move all detection, OCR, and evidence I/O to separate worker threads/processes.
  - Use `QThread` / `QObject.moveToThread()` for all blocking operations.
  - Implement `QProgressDialog` or status indicators for long operations.
- **Contingency Plan:**
  - Use `QApplication.processEvents()` as a last resort in compute loops.
  - Implement a timeout watchdog that kills stuck worker threads.
  - Profile and optimize the slowest UI-blocking operations.
- **Owner:** Frontend Engineer

---

### R-007 — Webhook Integration Failures with External Systems

- **Category:** Operational
- **Description:** External webhook endpoints may be unavailable, slow, return errors, or have incompatible payload formats.
- **Probability:** High
- **Impact:** Medium
- **Risk Score:** 6 (Medium)
- **Mitigation Strategy:**
  - Implement webhook retry with exponential backoff (3 attempts).
  - Add webhook timeout configuration (default 10s).
  - Log full request/response details for debugging.
- **Contingency Plan:**
  - Implement a webhook dead-letter queue for manual retry.
  - Allow users to test webhook configuration with a "Test" button.
  - Support custom body templates to match various API formats.
- **Owner:** Backend Engineer

---

### R-008 — Insufficient Disk Space for Evidence Storage

- **Category:** Operational
- **Description:** Continuous snapshot and video capture can consume disk space rapidly, potentially filling the drive and causing application or system failures.
- **Probability:** Medium
- **Impact:** High
- **Risk Score:** 6 (Medium)
- **Mitigation Strategy:**
  - Implement evidence retention policy (auto-purge after N days).
  - Monitor free disk space and warn at configurable thresholds (e.g., <10GB).
  - Allow user to configure evidence storage path (including external drives).
- **Contingency Plan:**
  - Automatically pause evidence capture when disk space falls below critical threshold.
  - Compress older evidence to reduce footprint.
  - Alert system administrator via tray notification and log entry.
- **Owner:** Backend Engineer

---

### R-009 — USB Camera Hot-Plug / Device Index Drift

- **Category:** Technical
- **Description:** USB cameras may change device index after system reboot or reconnection, causing the application to reference the wrong camera or fail to connect.
- **Probability:** Medium
- **Impact:** Medium
- **Risk Score:** 4 (Medium)
- **Mitigation Strategy:**
  - Enumerate USB cameras by serial number or hardware ID, not just index.
  - Store USB device identifier alongside index in camera config.
  - Implement reconnection logic that re-indexes USB devices on failure.
- **Contingency Plan:**
  - Add "Re-scan USB Devices" button in camera settings.
  - Show a warning when a configured USB camera index no longer matches the detected serial.
  - Fall back to index-based matching if serial is unavailable.
- **Owner:** CV/ML Engineer

---

### R-010 — Application Crash on Startup Due to Missing Dependencies

- **Category:** Technical
- **Description:** Required system dependencies (FFmpeg, CUDA/cuDNN for GPU, Visual C++ redistributables) may be missing or mismatched on the target machine.
- **Probability:** Medium
- **Impact:** High
- **Risk Score:** 6 (Medium)
- **Mitigation Strategy:**
  - Document all system dependencies in README and provide a setup script.
  - Check dependencies on startup and show clear error messages if missing.
  - Bundle portable versions of FFmpeg and other non-GPU dependencies.
- **Contingency Plan:**
  - Build with PyInstaller to include all Python dependencies in a single executable.
  - Provide a dependency installer script that auto-installs missing components.
  - Run in CPU-only mode if CUDA is unavailable.
- **Owner:** Backend Engineer

---

### R-011 — Schedule Overruns Due to Underestimated Effort

- **Category:** Schedule
- **Description:** The 4-sprint schedule (8 weeks) may be insufficient to deliver all features at the required quality level, especially Sprint 2 and Sprint 3 which have high story point totals.
- **Probability:** High
- **Impact:** High
- **Risk Score:** 9 (High)
- **Mitigation Strategy:**
  - Prioritize features within each sprint; identify must-have vs. nice-to-have.
  - Track velocity after Sprint 1 and adjust scope accordingly.
  - Use daily stand-ups to identify blockers early.
- **Contingency Plan:**
  - Add a 5th buffer sprint for remaining work and bug fixes.
  - Defer lower-priority features (e.g., US-028 export, US-019 manual capture) to post-launch.
  - Reduce scope of Sprint 4 if velocity is below target.
- **Owner:** Project Manager

---

### R-012 — YOLOv8 / PaddleOCR License Compliance

- **Category:** Resource
- **Description:** Both YOLOv8 (AGPL-3.0) and PaddleOCR (Apache 2.0) have license terms that may impose restrictions on commercial distribution or require attribution.
- **Probability:** Low
- **Impact:** Medium
- **Risk Score:** 2 (Low)
- **Mitigation Strategy:**
  - Review license terms for YOLOv8 (Ultralytics) and PaddleOCR.
  - Include appropriate attribution and license notices in the application.
  - If AGPL-3.0 is problematic, negotiate a commercial license with Ultralytics.
- **Contingency Plan:**
  - Replace YOLOv8 with a permissively licensed model (e.g., YOLOv5 under Apache 2.0).
  - Replace PaddleOCR with Tesseract (Apache 2.0) if needed.
- **Owner:** Project Manager / Legal

---

## Risk Heat Map

```
Impact →
  High    | R-005 R-008   | R-001          | R-010 R-011
          | R-012         | R-002 R-004    | R-003 R-006
          |               | R-009          | R-007
  Med     |               |                |
          |               |                |
  Low     |               |                |
          +---------------+---------------+---------------+
              Low             Med             High
                                        ← Probability
```

### Risk Priority Order (Highest to Lowest)

| Rank | ID | Risk | Score | Sprint | Action |
|------|----|------|-------|--------|--------|
| 1 | R-011 | Schedule Overruns | 9 | All | Prioritize features, track velocity |
| 2 | R-001 | YOLOv8 Performance | 6 | Sprint 2 | Benchmark early, use smaller model |
| 3 | R-003 | Camera Disconnects | 6 | Sprint 4 | Auto-reconnect, health checks |
| 4 | R-005 | Memory Leaks | 6 | Sprint 4 | Memory profiling, soak tests |
| 5 | R-006 | UI Freezing | 6 | All | Worker threads, async processing |
| 6 | R-007 | Webhook Failures | 6 | Sprint 3 | Retries, timeouts, test button |
| 7 | R-008 | Disk Space Exhaustion | 6 | Sprint 3 | Retention policies, disk monitoring |
| 8 | R-010 | Missing Dependencies | 6 | Sprint 1 | Startup checks, bundled executables |
| 9 | R-002 | OCR Accuracy | 4 | Sprint 2 | Early testing, fallback engines |
| 10 | R-004 | SQLite Contention | 4 | Sprint 3 | WAL mode, batch writes |
| 11 | R-009 | USB Device Drift | 4 | Sprint 2 | Serial-based enumeration |
| 12 | R-012 | License Compliance | 2 | Sprint 1 | Legal review, attribution |

---

## Monitoring & Review

- **Risk review cadence:** Weekly during sprint planning
- **Owner of risk register:** Project Manager
- **Trigger for escalation:** Any risk with score ≥ 6 that materializes
- **Risk burndown:** Track number of active high/medium risks each sprint

# User Stories

> **Project:** Plate Guard — AI License Plate Recognition Desktop Application
> **Document Version:** 1.0
> **Date:** 2026-06-15

---

## Epic 1: Camera Management

### US-001 — Add RTSP Camera
**As a** System Administrator,
**I want** to add an RTSP camera by providing its URL and a friendly name,
**so that** I can begin monitoring a remote location for license plates.

### US-002 — Add USB Camera
**As a** System Administrator,
**I want** to add a locally connected USB camera by selecting its device index,
**so that** I can use a webcam or USB camera as a detection source.

### US-003 — Edit Camera Configuration
**As a** System Administrator,
**I want** to edit an existing camera's name, URL, or USB index,
**so that** I can correct configuration errors without removing and re-adding the camera.

### US-004 — Delete Camera
**As a** System Administrator,
**I want** to delete a camera and all its associated data (zones, webhooks, detections),
**so that** I can clean up unused or decommissioned cameras.

### US-005 — Enable / Disable Camera
**As a** Security Guard,
**I want** to enable or disable a camera with a single toggle,
**so that** I can temporarily stop detection on a camera without losing its configuration.

### US-006 — View All Cameras
**As a** Security Guard,
**I want** to see a list of all configured cameras with their status (online/offline/enabled/disabled),
**so that** I can quickly assess the state of the monitoring system.

---

## Epic 2: Detection

### US-007 — Real-Time YOLOv8 Detection
**As a** Security Guard,
**I want** the application to run YOLOv8 on every camera frame in real time,
**so that** license plates are detected as soon as they appear in the field of view.

### US-008 — Configure Confidence Threshold per Camera
**As a** System Administrator,
**I want** to set a minimum confidence threshold per camera for detection,
**so that** I can reduce false positives and only capture high-confidence plates.

### US-009 — Display Bounding Box and Confidence
**As a** Security Guard,
**I want** to see bounding boxes and confidence scores overlaid on the live camera feed,
**so that** I can visually verify what the system is detecting.

---

## Epic 3: Detection Zones

### US-010 — Create Polygon Detection Zone
**As a** System Administrator,
**I want** to draw a polygon (3+ points) on a camera's live feed to define a detection zone,
**so that** only plates detected within that region trigger further processing.

### US-011 — Edit Detection Zone
**As a** System Administrator,
**I want** to adjust the vertices of an existing polygon zone,
**so that** I can refine the detection area without re-creating the zone from scratch.

### US-012 — Delete Detection Zone
**As a** System Administrator,
**I want** to delete a detection zone,
**so that** I can remove obsolete or unused zones.

### US-013 — Multiple Zones per Camera
**As a** System Administrator,
**I want** to assign multiple independent polygon zones to a single camera,
**so that** I can monitor different areas (e.g., entry gate and exit gate) with one camera.

---

## Epic 4: Optical Character Recognition

### US-014 — Automatic OCR on Detected Plates
**As a** Security Guard,
**I want** the system to automatically perform PaddleOCR on every detected license plate region,
**so that** the plate text is extracted without manual intervention.

### US-015 — OCR Confidence Score
**As a** Operations Manager,
**I want** each OCR result to include a confidence score,
**so that** I can judge the reliability of the recognized plate text and filter low-quality reads.

---

## Epic 5: Evidence Capture

### US-016 — Snapshot Capture on Detection
**As a** Security Guard,
**I want** a snapshot image of the detected plate to be saved automatically when a plate is recognized,
**so that** I have visual evidence of the event.

### US-017 — Video Clip Capture on Detection
**As a** Security Guard,
**I want** a video clip (3 seconds before and 3 seconds after the detection) to be saved automatically,
**so that** I have contextual video evidence of the event.

### US-018 — Configure Evidence Mode per Camera
**As a** System Administrator,
**I want** to choose per-camera whether to capture snapshots, video clips, or both,
**so that** I can balance storage usage against evidence needs.

### US-019 — Manual Evidence Capture
**As a** Security Guard,
**I want** to manually trigger a snapshot or video clip from the live feed at any time,
**so that** I can capture evidence outside of automatic detection events.

---

## Epic 6: Webhooks

### US-020 — Configure Webhook per Camera
**As a** System Administrator,
**I want** to configure a webhook endpoint per camera with method (GET/POST/PUT/PATCH), URL, headers, body, and auth,
**so that** detected plate data is forwarded to external systems.

### US-021 — Webhook Authentication
**As a** System Administrator,
**I want** to configure webhook authentication (None, Basic, Bearer, API Key),
**so that** external endpoints are protected from unauthorized requests.

### US-022 — Attach Image and Video to Webhook
**As a** Operations Manager,
**I want** the webhook payload to optionally include the snapshot image and/or video clip as attachments,
**so that** downstream systems can display evidence directly.

### US-023 — Retry Failed Webhooks
**As a** Operations Manager,
**I want** the system to retry failed webhook deliveries up to 3 times,
**so that** transient network failures do not result in lost data.

### US-024 — Webhook Delivery Status Logging
**As a** System Administrator,
**I want** the webhook delivery status (success/failure, HTTP code) to be recorded with the detection log,
**so that** I can audit and troubleshoot integration issues.

---

## Epic 7: Detection Logs

### US-025 — View Detection Logs
**As a** Security Guard,
**I want** to view a searchable list of all detection events with plate number, confidence, camera, and timestamp,
**so that** I can review historical detection activity.

### US-026 — Filter Detection Logs
**As a** Operations Manager,
**I want** to filter logs by camera, date range, and plate number,
**so that** I can quickly find specific events among thousands of records.

### US-027 — View Evidence from Logs
**As a** Security Guard,
**I want** to open the associated snapshot image and video clip directly from a log entry,
**so that** I can review evidence without navigating away from the logs view.

### US-028 — Export Detection Logs
**As a** Operations Manager,
**I want** to export detection logs to CSV or JSON,
**so that** I can analyze plate data in external tools or generate reports.

---

## Epic 8: Background Mode

### US-029 — Minimize to System Tray
**As a** Security Guard,
**I want** to minimize the application to the system tray so that it continues running in the background,
**so that** I can use my computer for other tasks without stopping plate detection.

### US-030 — Auto-Start with Windows
**As a** System Administrator,
**I want** the application to automatically start when Windows boots,
**so that** the monitoring system is always running after a reboot.

### US-031 — Auto-Reconnect on Camera Disconnect
**As a** System Administrator,
**I want** the application to automatically attempt to reconnect a camera when its stream drops,
**so that** detection resumes without manual intervention.

### US-032 — 24/7 Continuous Operation
**As a** Operations Manager,
**I want** the application to operate continuously without crashing or degrading performance,
**so that** license plate monitoring is always available.

---

## Epic 9: Non-Functional Requirements

### US-033 — Fast Startup
**As a** Security Guard,
**I want** the application to start and be ready within 5 seconds,
**so that** I can begin monitoring quickly when I launch the app.

### US-034 — Support 16 Cameras Simultaneously
**As a** System Administrator,
**I want** the application to support up to 16 cameras running detection simultaneously,
**so that** I can monitor a large facility with a single instance.

### US-035 — Performance Stability
**As a** Operations Manager,
**I want** the application to maintain stable CPU and memory usage during 24/7 operation,
**so that** the monitoring system does not degrade over time or consume excessive resources.

---

## Epic 10: System Administration

### US-036 — User-Friendly Dashboard
**As a** Security Guard,
**I want** a dashboard showing live camera feeds, recent detections, and system status at a glance,
**so that** I can monitor the entire system from a single screen.

### US-037 — Zone Visual Editor
**As a** System Administrator,
**I want** a visual polygon editor where I can click to place vertices on the camera feed,
**so that** creating and adjusting detection zones is intuitive and accurate.

### US-038 — Application Settings
**As a** System Administrator,
**I want** to configure global application settings (storage paths, retention policies, performance options),
**so that** the application behaves according to organizational policies.

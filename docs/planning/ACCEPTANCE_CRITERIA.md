# Acceptance Criteria

> **Project:** Plate Guard — AI License Plate Recognition Desktop Application
> **Document Version:** 1.0
> **Date:** 2026-06-15

---

## US-001 — Add RTSP Camera

- **Given** the user is on the Camera Management page,
  **When** they click "Add Camera",
  **Then** a form appears with fields: Name, Type (RTSP), RTSP URL.
- **Given** the user fills in a valid RTSP URL and a unique name,
  **When** they click "Save",
  **Then** the camera is saved to the database and appears in the camera list.
- **Given** the user enters an invalid or unreachable RTSP URL,
  **When** they click "Save",
  **Then** an error message is shown and the camera is not saved.
- **Given** the user enters a name that already exists,
  **When** they click "Save",
  **Then** a duplicate-name error is displayed.
- **Given** the user leaves required fields empty,
  **When** they click "Save",
  **Then** validation errors are shown for each required field.

---

## US-002 — Add USB Camera

- **Given** the user is on the Camera Management page,
  **When** they click "Add Camera" and select type "USB",
  **Then** a dropdown of available USB camera indices is shown.
- **Given** the user selects a USB index and provides a name,
  **When** they click "Save",
  **Then** the USB camera is saved and appears in the camera list.
- **Given** the selected USB index is already in use by another camera,
  **When** they click "Save",
  **Then** a conflict error is displayed.
- **Given** no USB cameras are detected on the system,
  **When** the user opens the USB add form,
  **Then** a "No USB cameras detected" message is shown and save is disabled.

---

## US-003 — Edit Camera Configuration

- **Given** a camera exists in the system,
  **When** the user clicks "Edit" on that camera,
  **Then** a pre-populated form appears with the current camera details.
- **Given** the user modifies the name and RTSP URL,
  **When** they click "Save",
  **Then** the changes are persisted and reflected in the camera list.
- **Given** the user changes the camera type from RTSP to USB,
  **When** they click "Save",
  **Then** the old RTSP URL field is cleared and the USB index selector appears.
- **Given** the user provides an invalid URL during edit,
  **When** they click "Save",
  **Then** a validation error is shown and changes are not saved.

---

## US-004 — Delete Camera

- **Given** a camera exists,
  **When** the user clicks "Delete",
  **Then** a confirmation dialog appears warning that all associated zones, webhooks, and detections will be deleted.
- **Given** the user confirms deletion,
  **When** they click "OK",
  **Then** the camera and all its related records are removed from the database.
- **Given** the user cancels the confirmation dialog,
  **When** they click "Cancel",
  **Then** no changes are made.
- **Given** a camera is currently streaming and running detection,
  **When** it is deleted,
  **Then** the stream is stopped and resources are released immediately.

---

## US-005 — Enable / Disable Camera

- **Given** a camera is currently enabled,
  **When** the user toggles it to disabled,
  **Then** detection stops immediately and the camera status shows "Disabled".
- **Given** a camera is currently disabled,
  **When** the user toggles it to enabled,
  **Then** detection resumes and the camera status shows "Enabled".
- **Given** a camera is toggled while a detection event is in progress,
  **When** the camera is disabled,
  **Then** the current event is completed before the camera stops.
- **Given** the application restarts,
  **Then** enabled/disabled states are restored from the database.

---

## US-006 — View All Cameras

- **Given** the user opens the Camera Management page,
  **Then** a table is displayed with columns: Name, Type, Status (Online/Offline/Enabled/Disabled), Last Detection.
- **Given** there are no cameras configured,
  **Then** an empty-state message is shown: "No cameras configured. Click 'Add Camera' to begin."
- **Given** a camera is online and streaming,
  **Then** its status indicator shows green/online.
- **Given** a camera stream is lost,
  **Then** the status updates to offline within 10 seconds.

---

## US-007 — Real-Time YOLOv8 Detection

- **Given** a camera is enabled and streaming,
  **When** a frame is captured,
  **Then** YOLOv8 inference runs on the frame within 100ms.
- **Given** YOLOv8 detects a potential license plate with confidence above the threshold,
  **Then** the bounding box coordinates are returned for further processing.
- **Given** YOLOv8 confidence is below the threshold,
  **Then** the detection is discarded and no further processing occurs.
- **Given** no camera frames are being received,
  **Then** YOLOv8 is not invoked and no error is raised.

---

## US-008 — Configure Confidence Threshold per Camera

- **Given** the user is editing a camera,
  **When** they modify the confidence threshold field,
  **Then** the value is persisted and used for all subsequent detections on that camera.
- **Given** the user enters a value outside 0.0–1.0,
  **When** they try to save,
  **Then** a validation error is displayed.
- **Given** the confidence threshold is 0.0,
  **Then** all detections are accepted (no filtering).
- **Given** the confidence threshold is 1.0,
  **Then** only perfect-confidence detections are accepted (practically, none).

---

## US-009 — Display Bounding Box and Confidence

- **Given** a camera feed is being viewed live,
  **When** YOLOv8 detects a plate above the threshold,
  **Then** a colored bounding box is drawn around the plate on the video feed.
- **Given** a bounding box is displayed,
  **Then** the confidence percentage is shown above or next to the box.
- **Given** multiple plates are detected in the same frame,
  **Then** each plate has its own bounding box and confidence label.
- **Given** a detected plate exits the frame or is no longer detected,
  **Then** the bounding box fades or is removed within 500ms.

---

## US-010 — Create Polygon Detection Zone

- **Given** the user is viewing a camera's live feed,
  **When** they enter zone-editing mode,
  **Then** they can click on the video to place polygon vertices.
- **Given** the user places at least 3 vertices,
  **Then** a polygon shape is drawn and can be finalized.
- **Given** the user places fewer than 3 vertices and tries to save,
  **Then** an error is shown: "At least 3 points are required."
- **Given** the user finalizes the polygon,
  **When** they provide a zone name and click "Save",
  **Then** the zone is saved to the database and displayed on the feed.
- **Given** a polygon is self-intersecting,
  **When** the user tries to save,
  **Then** a "Polygon is invalid" warning is shown.

---

## US-011 — Edit Detection Zone

- **Given** a zone exists,
  **When** the user enters edit mode for that zone,
  **Then** the polygon vertices are displayed as draggable handles on the feed.
- **Given** the user drags a vertex to a new position,
  **When** they save,
  **Then** the updated polygon is persisted.
- **Given** the user removes a vertex leaving fewer than 3,
  **When** they try to save,
  **Then** a validation error is shown.

---

## US-012 — Delete Detection Zone

- **Given** a zone exists,
  **When** the user clicks "Delete Zone",
  **Then** a confirmation dialog is shown.
- **Given** the user confirms deletion,
  **Then** the zone is removed from the database and removed from the visual display.
- **Given** the zone is the only zone on a camera,
  **When** deleted,
  **Then** detection reverts to the full-frame (no zone filtering).

---

## US-013 — Multiple Zones per Camera

- **Given** a camera has 0 zones,
  **When** detection runs,
  **Then** the entire frame is the detection area.
- **Given** a camera has 2+ zones,
  **When** a plate is detected outside all zones,
  **Then** it is ignored (no OCR, no evidence).
- **Given** a camera has 2+ zones,
  **When** a plate is detected inside at least one zone,
  **Then** processing proceeds normally.
- **Given** zones overlap,
  **When** a plate falls in the overlapping area,
  **Then** it is processed once (duplicate detection is filtered).

---

## US-014 — Automatic OCR on Detected Plates

- **Given** YOLOv8 has detected a plate inside a valid zone,
  **When** the plate image is cropped from the frame,
  **Then** PaddleOCR is invoked on the cropped image.
- **Given** PaddleOCR returns recognized text,
  **Then** the text is stored as the plate number.
- **Given** PaddleOCR fails or returns empty text,
  **Then** the detection event is logged with an empty plate number and low-confidence marker.

---

## US-015 — OCR Confidence Score

- **Given** PaddleOCR returns a result,
  **Then** the confidence score (0.0–1.0) is stored alongside the plate text.
- **Given** the OCR confidence is below a configurable threshold (default 0.5),
  **When** the detection is logged,
  **Then** a "Low OCR Confidence" flag is attached to the log entry.

---

## US-016 — Snapshot Capture on Detection

- **Given** a detection event occurs with evidence mode set to "Snapshot" or "Both",
  **Then** a JPEG/PNG image of the full frame is saved to disk within 1 second.
- **Given** the snapshot is saved,
  **Then** the file path is recorded in the detection log.
- **Given** disk space is insufficient,
  **Then** an error is logged and the detection is still recorded (without image).
- **Given** the snapshot is saved,
  **Then** the file name follows the pattern `{camera_name}_{timestamp}_snapshot.jpg`.

---

## US-017 — Video Clip Capture on Detection

- **Given** a detection event occurs with evidence mode set to "Video" or "Both",
  **Then** a video clip of 6 seconds total (3s pre + 3s post) is saved.
- **Given** the video clip is saved,
  **Then** the file path is recorded in the detection log.
- **Given** the detection occurs within 3 seconds of application start (no buffer),
  **Then** the clip contains whatever buffer is available (shortened pre-roll).
- **Given** the detection occurs near the end of a long session,
  **Then** the clip is saved correctly without exceeding available disk space.
- **Given** the video is saved,
  **Then** the file name follows the pattern `{camera_name}_{timestamp}_clip.mp4`.

---

## US-018 — Configure Evidence Mode per Camera

- **Given** the user is editing a camera,
  **When** they select evidence mode from [None, Snapshot, Video, Both],
  **Then** the setting is persisted and used for all future detections.
- **Given** evidence mode is "None",
  **Then** no snapshot or video is captured on detection.
- **Given** evidence mode is changed from "Both" to "Snapshot",
  **Then** video capture stops immediately, snapshot capture continues.

---

## US-019 — Manual Evidence Capture

- **Given** the user is viewing a live camera feed,
  **When** they click "Capture Snapshot",
  **Then** a snapshot is saved immediately regardless of detection state.
- **Given** the user clicks "Record Clip",
  **Then** a 6-second video clip (3s before + 3s after click) is saved.
- **Given** a manual capture is saved,
  **Then** it is logged in the detection log with camera ID and "Manual" event type.

---

## US-020 — Configure Webhook per Camera

- **Given** the user is on the Camera Edit page,
  **When** they navigate to the Webhook section,
  **Then** fields for Method, URL, Headers (key-value), and Body template are displayed.
- **Given** the user configures a valid URL and method,
  **When** they save,
  **Then** the webhook configuration is persisted.
- **Given** the user provides an invalid URL,
  **When** they save,
  **Then** a validation error is shown.
- **Given** the webhook is saved,
  **Then** it is invoked for every subsequent detection event.

---

## US-021 — Webhook Authentication

- **Given** the user selects auth type "None",
  **Then** no auth header is added to the webhook request.
- **Given** the user selects auth type "Basic",
  **When** they provide username:password,
  **Then** a Base64-encoded `Authorization: Basic` header is included.
- **Given** the user selects auth type "Bearer",
  **When** they provide a token,
  **Then** an `Authorization: Bearer <token>` header is included.
- **Given** the user selects auth type "API Key",
  **When** they provide a key name and value,
  **Then** the specified header `X-API-Key: <value>` (or custom header name) is included.

---

## US-022 — Attach Image and Video to Webhook

- **Given** evidence mode includes snapshots and `send_image` is enabled,
  **When** the webhook is sent,
  **Then** the image file is attached as a multipart/form-data field or as a base64 field in JSON.
- **Given** evidence mode includes video and `send_video` is enabled,
  **Then** the video file is attached similarly.
- **Given** no evidence file exists for the detection,
  **Then** the webhook is sent without the attachment (no error).

---

## US-023 — Retry Failed Webhooks

- **Given** a webhook request returns a non-2xx status or a network error,
  **When** the first attempt fails,
  **Then** up to 2 additional retries are attempted with exponential backoff (1s, 4s).
- **Given** all retries fail,
  **Then** the webhook status is logged as "Failed" with the last error message.
- **Given** a retry succeeds,
  **Then** the webhook status is logged as "Success with retry".

---

## US-024 — Webhook Delivery Status Logging

- **Given** a detection event with a configured webhook,
  **Then** the webhook_status field in the detections table is updated to "Pending", "Success", or "Failed".
- **Given** the webhook status is "Failed",
  **Then** the HTTP status code and error message are recorded.
- **Given** there is no webhook configured for the camera,
  **Then** the webhook_status is "Not Configured".

---

## US-025 — View Detection Logs

- **Given** the user navigates to the Logs page,
  **Then** a paginated table of detection events is displayed with columns: Timestamp, Camera, Plate Number, Confidence, Webhook Status.
- **Given** there are no detection events,
  **Then** an empty-state message is shown: "No detections recorded yet."
- **Given** there are more than 100 events,
  **Then** pagination controls are available (Previous/Next, page numbers).

---

## US-026 — Filter Detection Logs

- **Given** the user is on the Logs page,
  **When** they select a camera from the dropdown filter,
  **Then** only detections from that camera are shown.
- **Given** the user selects a date range (start/end),
  **Then** only detections within that range are shown.
- **Given** the user types a partial plate number in the search box,
  **Then** only detections with matching plate numbers (substring, case-insensitive) are shown.
- **Given** multiple filters are active simultaneously,
  **Then** all filters are applied together (AND logic).

---

## US-027 — View Evidence from Logs

- **Given** a log entry has an associated snapshot,
  **When** the user clicks "View Image",
  **Then** the image is displayed in a modal or preview pane.
- **Given** a log entry has an associated video clip,
  **When** the user clicks "Play Video",
  **Then** the video is played in a media player component.
- **Given** a log entry has no evidence (mode was "None"),
  **Then** the image/video buttons are disabled or hidden.

---

## US-028 — Export Detection Logs

- **Given** the user has filters applied,
  **When** they click "Export CSV",
  **Then** a CSV file is downloaded containing all matching detection records with columns: ID, Camera, Plate Number, Confidence, Timestamp, Webhook Status.
- **Given** the user clicks "Export JSON",
  **Then** a JSON file is downloaded with the same data.
- **Given** there are no matching records,
  **When** the user attempts to export,
  **Then** a message is shown: "No data to export."

---

## US-029 — Minimize to System Tray

- **Given** the application is running in windowed mode,
  **When** the user clicks the minimize button or selects "Minimize to Tray",
  **Then** the window is hidden and an icon appears in the system tray.
- **Given** the application is in the system tray,
  **When** the user double-clicks the tray icon,
  **Then** the main window is restored.
- **Given** the application is in the system tray,
  **When** the user right-clicks the tray icon,
  **Then** a context menu appears with options: Show, Pause Detection, Settings, Exit.

---

## US-030 — Auto-Start with Windows

- **Given** the user enables "Auto-start with Windows" in Settings,
  **Then** a shortcut or registry entry is created so the application launches at boot.
- **Given** the user disables "Auto-start with Windows",
  **Then** the shortcut or registry entry is removed.
- **Given** the application is launched via auto-start,
  **Then** it starts minimized to the system tray (no main window shown on boot).

---

## US-031 — Auto-Reconnect on Camera Disconnect

- **Given** a camera stream drops unexpectedly,
  **When** the disconnect is detected,
  **Then** the camera status is set to "Reconnecting" and a reconnection timer starts.
- **Given** the reconnection timer fires,
  **When** the stream becomes available again,
  **Then** the stream is re-established and status returns to "Online".
- **Given** reconnection fails after 5 attempts (with 10s interval),
  **Then** the camera status is set to "Offline" and an alert is logged.
- **Given** a camera is reconnecting,
  **When** the user manually disables and re-enables the camera,
  **Then** the reconnection is reset and a fresh attempt is made.

---

## US-032 — 24/7 Continuous Operation

- **Given** the application runs for 7 continuous days,
  **Then** there is no memory leak (memory usage remains within 20% of starting baseline).
- **Given** the application encounters an unhandled exception in a worker thread,
  **Then** the error is caught, logged, and does not crash the main application.
- **Given** the application runs continuously,
  **Then** all database operations complete within acceptable timeframes (no accumulating WAL file).

---

## US-033 — Fast Startup

- **Given** the application is launched,
  **When** the user clicks the executable,
  **Then** the main window is displayed and interactive within 5 seconds.
- **Given** the application has 16 cameras configured,
  **When** it starts,
  **Then** the UI is responsive within 5 seconds (cameras may connect in background after that).
- **Given** the application starts with no cameras configured,
  **Then** the empty dashboard is displayed within 3 seconds.

---

## US-034 — Support 16 Cameras Simultaneously

- **Given** 16 cameras are enabled and streaming,
  **Then** all 16 feeds are processed at a minimum of 5 FPS each.
- **Given** 16 cameras are active,
  **Then** CPU usage does not exceed 80% on a modern i7 or equivalent.
- **Given** 16 cameras are active,
  **Then** the UI remains responsive with no input lag exceeding 500ms.

---

## US-035 — Performance Stability

- **Given** the application runs for 24 hours,
  **Then** CPU usage does not increase by more than 10% compared to the first hour.
- **Given** the application runs detection on all cameras,
  **Then** YOLOv8 inference does not cause frame processing to fall behind by more than 30 frames.
- **Given** a detection event occurs while previous evidence is still being saved,
  **Then** the new detection is queued and processed without data loss.

---

## US-036 — User-Friendly Dashboard

- **Given** the user opens the application,
  **Then** the dashboard shows live thumbnail feeds of all enabled cameras in a grid layout.
- **Given** there are recent detection events,
  **Then** a "Recent Detections" panel shows the last 10 events with plate number, camera, and timestamp.
- **Given** a camera's stream is offline,
  **Then** the thumbnail shows a "Camera Offline" placeholder image.
- **Given** the user clicks a camera thumbnail,
  **Then** the full live feed for that camera is opened in the Detection Viewer.

---

## US-037 — Zone Visual Editor

- **Given** the user is in zone editing mode,
  **When** they click on the video feed,
  **Then** a vertex marker is placed at the click position.
- **Given** vertices are placed,
  **When** the user hovers over a vertex,
  **Then** the cursor changes to a move handle.
- **Given** the user drags a vertex,
  **Then** the polygon updates in real time.
- **Given** the user right-clicks a vertex,
  **Then** that vertex is removed.
- **Given** the user places a vertex that causes the polygon to self-intersect,
  **Then** the polygon fill turns red to indicate an invalid shape.

---

## US-038 — Application Settings

- **Given** the user opens Settings,
  **Then** sections are available for: Storage (evidence save path), Retention (max days to keep logs/evidence), Performance (max cameras, FPS limit), and General (language, theme).
- **Given** the user changes the evidence save path,
  **When** they click "Apply",
  **Then** new evidence is saved to the new path (existing evidence is not moved).
- **Given** the user sets a retention policy of 30 days,
  **Then** evidence and logs older than 30 days are purged daily at midnight.

# Sequence Diagrams

> **Project:** Plate Guard — AI License Plate Recognition Desktop Application
> **Version:** 1.0
> **Date:** 2026-06-15

---

> All diagrams use Mermaid syntax. Render them with any Mermaid-compatible viewer or paste into a Mermaid live editor.

---

## 1. Add Camera Flow

```mermaid
sequenceDiagram
    actor Admin as System Administrator
    participant UI as CameraManagementView
    participant Service as CameraService
    participant Repo as CameraRepository
    participant DB as SQLite
    participant Cam as CameraStream (Validation)

    Admin->>UI: Click "Add Camera"
    UI->>UI: Show AddCameraForm
    Admin->>UI: Fill name, type (RTSP), URL, threshold
    Admin->>UI: Click "Save"

    UI->>Service: add_camera(name, type, rtsp_url, ...)

    Service->>Service: Validate inputs
    alt Invalid input
        Service-->>UI: Raise ValueError
        UI->>Admin: Show validation error
    end

    Service->>Repo: exists_by_name(name)
    Repo->>DB: SELECT count(*) FROM cameras WHERE name=?
    DB-->>Repo: count
    alt Name exists
        Repo-->>Service: True
        Service-->>UI: Raise DuplicateNameError
        UI->>Admin: Show "Name already exists"
    end

    Service->>Cam: validate_connection(rtsp_url)
    alt Connection fails
        Cam-->>Service: ConnectionError
        Service-->>UI: Raise CameraConnectionError
        UI->>Admin: Show "Unable to connect to camera"
    end

    Service->>Repo: add(camera)
    Repo->>DB: INSERT INTO cameras (...)
    DB-->>Repo: camera with id
    Repo-->>Service: Camera
    Service-->>UI: Camera
    UI->>UI: Refresh camera list
    UI->>Admin: Show success notification
```

---

## 2. Detection Pipeline (Inner Loop)

```mermaid
sequenceDiagram
    participant Capture as FrameCapture (per camera)
    participant Pipeline as DetectionPipeline
    participant YOLO as YOLOv8Engine
    participant Zone as ZoneValidator
    participant Tracker as PlateTracker
    participant DupFilter as DuplicateFilter

    loop Every frame (≈33ms at 30 FPS)
        Capture->>Pipeline: new_frame(frame, timestamp)

        Pipeline->>YOLO: detect(frame)
        YOLO->>YOLO: Run inference
        YOLO-->>Pipeline: list[BoundingBox]

        alt No detections
            Pipeline->>Pipeline: Skip frame
        end

        loop For each detected BoundingBox
            Pipeline->>Zone: is_inside_any_zone(bbox_center, camera_id)
            Zone->>Zone: Point-in-polygon test
            alt Outside all zones
                Zone-->>Pipeline: False
                Pipeline->>Pipeline: Discard detection
            else Inside a zone
                Zone-->>Pipeline: True
            end

            Pipeline->>Tracker: update(bbox, camera_id)
            Tracker->>Tracker: Associate with existing track or create new
            Tracker-->>Pipeline: track_id

            Pipeline->>DupFilter: is_duplicate(track_id, plate_text?)
            alt Is duplicate (same plate in last 5s)
                DupFilter-->>Pipeline: True
                Pipeline->>Pipeline: Suppress detection
            else
                DupFilter-->>Pipeline: False
                Pipeline->>Pipeline: Emit PlateDetected event
                Pipeline->>OCR: recognize(frame, bbox)
            end
        end
    end
```

---

## 3. Full Detection Event (OCR → Evidence → Webhook → Log)

```mermaid
sequenceDiagram
    participant Pipe as DetectionPipeline
    participant OCR as OCRService
    participant Record as RecordingService
    participant Webhook as WebhookService
    participant Log as LoggingService
    participant Disk as File System
    participant DB as SQLite

    Note over Pipe,DB: Triggered by Pipe after duplicate filter

    Pipe->>OCR: recognize(frame, bbox)
    OCR->>OCR: Crop plate region
    OCR->>OCR: Run PaddleOCR inference
    OCR-->>Pipe: OCRResult(text, confidence)

    Pipe->>Pipe: Create Detection entity

    alt Evidence mode = Snapshot or Both
        Pipe->>Record: save_snapshot(camera_id, frame)
        Record->>Disk: Write JPEG file
        Disk-->>Record: image_path
        Record-->>Pipe: image_path
    end

    alt Evidence mode = Video or Both
        Pipe->>Record: save_video_clip(camera_id, timestamp)
        Record->>Record: Assemble clip from ring buffer
        Record->>Disk: Write MP4 file
        Disk-->>Record: video_path
        Record-->>Pipe: video_path
    end

    Pipe->>Log: log_detection(Detection)
    Log->>DB: INSERT INTO detections (...)
    DB-->>Log: Detection with id
    Log-->>Pipe: Detection (saved)

    alt Camera has webhook configured
        Pipe->>Webhook: send_async(Detection, Camera)
        Webhook->>Webhook: Prepare payload with auth
        alt send_image or send_video enabled
            Webhook->>Disk: Read file(s)
            Disk-->>Webhook: binary data
        end
        Webhook->>Webhook: POST/PUT to endpoint URL
        alt Success (2xx)
            Webhook-->>Pipe: WebhookStatus.SUCCESS
        else Failure or retry exhausted
            Webhook-->>Pipe: WebhookStatus.FAILED
        end
        Pipe->>Log: update_webhook_status(detection.id, status)
        Log->>DB: UPDATE detections SET webhook_status=?
    else
        Pipe->>Pipe: WebhookStatus = NOT_CONFIGURED
    end

    Pipe->>Pipe: Event fully processed
```

---

## 4. Webhook Delivery with Retry

```mermaid
sequenceDiagram
    participant Pipe as DetectionPipeline
    participant WH as WebhookService
    participant Client as httpx.AsyncClient
    participant Target as External Webhook Server
    participant Log as LoggingService
    participant DB as SQLite

    Pipe->>WH: send_async(detection, camera)
    WH->>WH: Build request (method, URL, headers, body, auth)
    WH->>WH: Attach image/video if configured

    Note over WH: Attempt 1
    WH->>Client: request(method, url, ...)
    Client->>Target: HTTP call
    alt 2xx response
        Target-->>Client: 200 OK
        Client-->>WH: Response
        WH-->>Log: webhook_status = SUCCESS
        Log->>DB: UPDATE detections SET status='success'
        WH-->>Pipe: SUCCESS
    else 5xx or network error
        Target-->>Client: 500 / timeout
        Client-->>WH: RequestError / HTTPStatusError

        Note over WH: Wait 1s (exponential backoff)

        Note over WH: Attempt 2
        WH->>Client: request(method, url, ...)
        Client->>Target: HTTP call
        alt 2xx response
            Target-->>Client: 200 OK
            Client-->>WH: Response
            WH-->>Log: webhook_status = SUCCESS (with retry)
            Log->>DB: UPDATE detections
            WH-->>Pipe: SUCCESS
        else failure again
            Note over WH: Wait 4s

            Note over WH: Attempt 3 (final)
            WH->>Client: request(method, url, ...)
            Client->>Target: HTTP call
            alt 2xx response
                Target-->>Client: 200 OK
                Client-->>WH: Response
                WH-->>Log: webhook_status = SUCCESS (with retry)
            else all fail
                Client-->>WH: error
                WH-->>Log: webhook_status = FAILED, error msg
                Log->>DB: UPDATE detections SET status='failed', error=?
                WH-->>Pipe: FAILED
            end
        end
    end
```

---

## 5. Manual Evidence Capture

```mermaid
sequenceDiagram
    actor Guard as Security Guard
    participant UI as DetectionViewer
    participant Record as RecordingService
    participant Log as LoggingService
    participant Disk as File System
    participant DB as SQLite

    alt Manual Snapshot
        Guard->>UI: Click "Capture Snapshot"
        UI->>UI: Freeze current frame
        UI->>Record: manual_snapshot(camera_id, frame)
        Record->>Disk: Write {camera}_{timestamp}_snapshot.jpg
        Disk-->>Record: image_path
        Record-->>UI: image_path
        UI->>Log: log_detection(manual_event)
        Log->>DB: INSERT INTO detections (...)
        UI->>Guard: Show "Snapshot saved" notification
    end

    alt Manual Video Clip
        Guard->>UI: Click "Record Clip"
        UI->>Record: manual_clip(camera_id)
        Record->>Record: Read ring buffer (last 3s)
        Record->>Record: Continue recording for 3 more seconds
        Record->>Disk: Write {camera}_{timestamp}_clip.mp4
        Disk-->>Record: video_path
        Record-->>UI: video_path
        UI->>Log: log_detection(manual_event)
        Log->>DB: INSERT INTO detections (...)
        UI->>Guard: Show "Clip saved" notification
    end
```

---

## 6. Camera Disconnect & Auto-Reconnect

```mermaid
sequenceDiagram
    participant Cam as CameraStream
    participant Monitor as CameraHealthMonitor
    participant Service as CameraService
    participant Pipeline as DetectionPipeline
    participant UI as CameraManagementView

    Note over Cam,UI: Steady state: camera is online

    Cam--xMonitor: Frame capture timeout (no frame for 5s)
    Monitor->>Monitor: Increment failure counter
    alt Failure count < threshold
        Monitor->>Cam: Request keyframe / send keepalive
    else Failure count >= threshold
        Monitor->>Service: _on_disconnect(camera_id)
        Service->>UI: Signal: camera_status_changed(OFFLINE)
        UI->>UI: Update camera status indicator

        Service->>Service: Set status = RECONNECTING
        Service->>UI: Signal: camera_status_changed(RECONNECTING)
        UI->>UI: Show "Reconnecting..." overlay

        loop Up to 5 attempts with 10s interval
            Service->>Cam: reconnect()
            alt Connection successful
                Cam-->>Service: OK
                Service->>Pipeline: start_camera(camera_id)
                Service->>Service: Set status = ONLINE
                Service->>UI: Signal: camera_status_changed(ONLINE)
                UI->>UI: Clear error state, resume feed
            else Connection failed
                Cam-->>Service: ConnectionError
                Service->>Service: Log error, wait 10s
            end
        end

        alt All 5 attempts failed
            Service->>Service: Set status = OFFLINE
            Service->>UI: Signal: camera_status_changed(OFFLINE)
            UI->>UI: Show "Camera Offline" indicator
            Service->>Service: Log critical alert
        end

        Note over Service,UI: Manual enable will reset and retry
    end
```

---

## 7. Application Startup

```mermaid
sequenceDiagram
    participant OS as Operating System
    participant Main as main.py
    participant App as Application
    participant DI as ServiceContainer
    participant DB as SQLite
    participant Svc as CameraService
    participant Det as DetectionService
    participant UI as DashboardWindow
    participant Tray as SystemTray

    OS->>Main: Launch process
    Main->>Main: Parse CLI args, configure logging
    Main->>App: Application(config, di_container)

    App->>App: Register Qt application (QApplication)
    App->>DI: Initialize dependency injection container

    DI->>DB: Create engine, check connection
    DI->>DB: Run migrations (Alembic upgrade)
    DB-->>DI: Schema up-to-date

    DI->>DI: Wire repositories (CameraRepo, DetectionRepo, etc.)
    DI->>DI: Wire services (CameraSvc, DetectionSvc, etc.)

    App->>Svc: get_all_cameras()
    Svc->>Svc: Load from DB
    Svc-->>App: list[Camera]

    App->>UI: Create DashboardWindow
    App->>Tray: Create SystemTrayIcon

    App->>Det: start_all()
    Det->>Det: For each enabled camera, spawn worker thread
    Det-->>App: Detection running

    UI->>UI: Render live camera grid
    UI->>App: Show window

    Note right of App: Total startup: <5 seconds
```

---

## 8. Minimize to System Tray

```mermaid
sequenceDiagram
    actor Guard as Security Guard
    participant Window as MainWindow
    participant App as Application
    participant Tray as SystemTrayIcon
    participant Menu as TrayContextMenu
    participant Det as DetectionService

    Guard->>Window: Click minimize button
    Window->>Window: closeEvent / changeEvent
    Window->>App: on_minimize_to_tray()
    App->>Tray: show()
    App->>Window: hide()

    Note over Guard,Tray: Application continues running in background

    Guard->>Tray: Right-click tray icon
    Tray->>Tray: Show context menu
    Tray-->>Guard: Menu: Show, Pause, Settings, Exit

    alt Click "Show"
        Guard->>Tray: Click "Show"
        Tray->>App: restore_window()
        App->>Window: show() / raise()
        Window-->>Guard: Window restored
    end

    alt Click "Pause Detection"
        Guard->>Tray: Click "Pause"
        Tray->>App: toggle_pause()
        App->>Det: pause()
        Menu->>Menu: Update label to "Resume Detection"
    end

    alt Click "Exit"
        Guard->>Tray: Click "Exit"
        Tray->>App: shutdown()
        App->>Det: stop_all()
        App->>App: Flush buffers, close DB, release resources
        App->>App: QApplication.quit()
    end
```

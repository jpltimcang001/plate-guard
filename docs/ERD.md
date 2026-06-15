# Database Design

## cameras

| Field | Type |
|---------|---------|
| id | INTEGER |
| name | TEXT |
| type | TEXT |
| rtsp_url | TEXT |
| usb_index | INTEGER |
| enabled | INTEGER |
| confidence_threshold | REAL |

---

## zones

| Field | Type |
|---------|---------|
| id | INTEGER |
| camera_id | INTEGER |
| name | TEXT |
| polygon_json | TEXT |

---

## webhooks

| Field | Type |
|---------|---------|
| id | INTEGER |
| camera_id | INTEGER |
| method | TEXT |
| url | TEXT |
| headers_json | TEXT |
| auth_type | TEXT |
| auth_value | TEXT |
| body_template | TEXT |
| send_image | INTEGER |
| send_video | INTEGER |

---

## detections

| Field | Type |
|---------|---------|
| id | INTEGER |
| camera_id | INTEGER |
| plate_number | TEXT |
| confidence | REAL |
| image_path | TEXT |
| video_path | TEXT |
| webhook_status | TEXT |
| detected_at | DATETIME |
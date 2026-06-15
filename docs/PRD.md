# Product Requirements Document

# Project

AI License Plate Recognition Desktop Application

---

# Objective

Develop a production-ready desktop application capable of:

- Managing RTSP cameras
- Managing USB cameras
- Detecting license plates
- Recognizing license plates
- Triggering webhooks
- Capturing evidence
- Running in the background

---

# Features

## Camera Management

### Functional Requirements

- Add Camera
- Edit Camera
- Delete Camera
- Enable Camera
- Disable Camera

Supported Sources:

- RTSP
- USB

---

## Detection

Use YOLOv8 model.

Capabilities:

- Real-time detection
- Bounding box display
- Confidence display
- Confidence threshold filtering

---

## Detection Zones

Each camera can have multiple zones.

Requirements:

- Minimum 3 points
- Unlimited points
- Polygon support
- Visual editor

---

## OCR

Requirements:

- Extract plate image
- Recognize text
- Return confidence score

---

## Evidence Capture

Options:

- Snapshot
- Video
- Snapshot + Video

Video Length:

- 3 seconds before event
- 3 seconds after event

---

## Webhooks

Per Camera Configuration

Supported Methods:

- GET
- POST
- PUT
- PATCH

Authentication:

- None
- Basic
- Bearer
- API Key

Custom:

- URL
- Headers
- Body

Attachments:

- Image
- Video

---

## Detection Logs

Store:

- Camera
- Plate Number
- Confidence
- Timestamp
- Image
- Video
- Webhook Status

Filters:

- Camera
- Date Range
- Plate Number

---

## Background Mode

Capabilities:

- Minimize to tray
- Auto start
- Auto reconnect cameras

---

# Non Functional Requirements

- Startup under 5 seconds
- Support 16 cameras
- Recover from camera disconnects
- Operate continuously 24/7
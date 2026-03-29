**Media ingest (current frontend):** JPEG still frames from the camera every **15 seconds**, posted via `multipart/form-data` to `POST /agent/process-capture`. The backend frame-filtering module applies to those JPEG payloads: accepted frames go through OCR → `visual_delta` text → graph agent. Audio is recorded **locally** in the browser only and is never sent to the server.

---

# Backend Notes

This document is the plain-language backend status snapshot for the team.

## System Overview

- Client
- ↓
- Session Service (timer + state)
- ↓
- Question Service (select + lock question)
- ↓
- Collection Phase
- ↓
- Evaluation Pipeline (hint/review)
- ↓
- AI Evaluation Service
- ↓
- Response (hint / score / next step)

## Where The Backend Is Right Now

The backend is a Python service using Starlette + Uvicorn.

There are currently two backend tracks in the repo:

- The active system-design session backend (HTTP API + Gemini agent)
- The visual-delta pipeline that converts relevant frame changes into text for the agent

The system-design backend is responsible for managing a live architecture graph during an interview session and saving it to MongoDB when the session ends.

The visual pipeline is responsible for deciding whether an incoming frame is worth keeping, extracting relevant text and simple structure from it, and producing a plain-English `visual_delta` string.

## Key Components

When a user begins, we start a timed session. Hints pause the timer and resume after the hint is generated. Review ends the timer.

- Question bank
  Stores architecture prompts in a format the AI can read consistently. The frontend receives one selected question for the session, and the backend keeps the matching solution context available for evaluation.

- Collection phase
  The frontend captures JPEG stills from the camera every 15 seconds and posts them to the backend. The backend and agent stack use those frames to build an understanding of the user's architecture over time.

- Review or hint
  Hint returns a suggestion for the frontend to display. Review returns a grade, improvement guidance, and can decide whether to continue with follow-up or correction flow.

## Current Backend Pieces

- `backend/main.py`
  Starts the backend server.

- `backend/server/app.py`
  Starlette HTTP server — session management and all HTTP endpoints.

- `backend/core/graph.py`
  Stores the in-memory graph of the user's architecture.

- `backend/core/session_store.py`
  Saves a finished session to MongoDB.

- `backend/core/frame_processor.py`
  Filters incoming frames before any expensive downstream processing.

- `backend/core/visual_delta_pipeline.py`
  Runs OCR, groups relevant text, detects simple connections, and emits `visual_delta`.

## Current Agent / Collection Direction

The backend collection pipeline:

- Frontend posts JPEG frames to `POST /agent/process-capture` every 15 seconds
- Environment includes `GOOGLE_API_KEY` support for Gemini-based multimodal workflows
- LangChain and Gemini packages are now part of backend dependencies

This means the backend has a staged visual pipeline that turns raw JPEG frames into structured graph updates via the Gemini agent.

## What The Visual Pipeline Does

The visual pipeline is the important middle layer between image input and agent reasoning.

Processing order:

1. Decode the incoming image
2. Run person detection
3. If a person is detected, drop the frame immediately
4. Compare the frame against the last accepted frame using a fast grayscale diff
5. If the frame is too similar, drop it
6. Run OCR on the accepted frame
7. Separate OCR text into likely component labels and nearby annotation text
8. Detect simple line-based connections between components
9. Compare the current OCR snapshot to the last accepted OCR snapshot
10. Generate a plain-English `visual_delta` string

This means the backend has a real staged path for visual understanding instead of sending raw frames straight into the graph agent.

## What Is Implemented In The Visual Pipeline

- Accepts image input as base64, bytes, or a NumPy array
- Uses OpenCV to decode images
- Uses YOLOv8 nano through `ultralytics` for person detection
- Only checks for the `person` class
- Uses grayscale + resize + mean absolute difference for fast similarity checks
- Compares new frames only against the last accepted frame
- Uses local `tesseract` OCR on accepted frames
- Detects component text, nearby annotation text, and simple connections
- Produces `visual_delta` strings such as:
  - `A box labeled 'Redis Cache' was drawn with an arrow from 'API Service'.`
  - `Text '3 replicas' was added near 'API Service'.`
  - `An arrow was drawn from 'Browser' to 'API'.`

## What Is Still Rough

- OCR grouping is heuristic, not production-grade
- Arrow detection is still simple line proximity logic
- Annotation-to-component attachment is approximate
- The pipeline is good for iteration, but real whiteboard footage will need tuning

## Environment Variables

- `MONGODB_URI`
  MongoDB Atlas connection string

- `GOOGLE_API_KEY`
  Google AI Studio key for Gemini access

## Installation Status

The backend dependency list now includes the packages needed for the frame pipeline:

- `numpy`
- `opencv-python`
- `ultralytics`
- local `tesseract`

The packaging config in `backend/pyproject.toml` was also updated so editable installs work with the current multi-package backend layout.

## Recommended Next Backend Steps

- Tune OCR preprocessing on real whiteboard frames
- Improve connection detection beyond simple Hough-line proximity
- Improve annotation attachment so notes are more reliably linked to the correct component
- Add end-to-end tests using saved image sequences

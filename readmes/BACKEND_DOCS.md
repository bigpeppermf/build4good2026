**Media ingest (current frontend):** live **video + audio** as WebM `MediaRecorder` chunks over a **WebSocket** (`/api/practice/stream`). Spec: [STREAMING.md](STREAMING.md). The older periodic JPEG snapshot flow has been replaced in the frontend, but the backend frame-filtering module still exists as an isolated building block for future visual pipelines.

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

The backend is now a Python service, not the old TypeScript Express server.

There are currently two backend tracks in the repo:

- The active system-design session backend
- The new frame-processing gatekeeper that filters incoming images before more expensive work happens

The active backend now includes a streaming contract for live practice media ingestion over WebSocket, plus AI-driven graph/session infrastructure behind the scenes.

The system-design backend is responsible for managing a live architecture graph during an interview session and saving it to MongoDB when the session ends.

The frame-processing module is responsible for deciding whether an incoming frame is worth keeping at all.

## Key Components

When a user begins, we start a timed session. Hints pause the timer and resume after the hint is generated. Review ends the timer.

- Question bank
  Stores architecture prompts in a format the AI can read consistently. The frontend receives one selected question for the session, and the backend keeps the matching solution context available for evaluation.

- Collection phase
  The current frontend sends live media over WebSocket. The backend and agent stack use that session media to build an understanding of the user's architecture over time.

- Review or hint
  Hint returns a suggestion for the frontend to display. Review returns a grade, improvement guidance, and can decide whether to continue with follow-up or correction flow.

## Current Backend Pieces

- `backend/main.py`
  Starts the backend server.

- `backend/graph_mcp/server.py`
  Hosts the MCP server and exposes graph-editing tools for the AI.

- `backend/core/graph.py`
  Stores the in-memory graph of the user's architecture.

- `backend/core/session_store.py`
  Saves a finished session to MongoDB.

- `backend/core/frame_processor.py`
  Filters incoming frames before any expensive downstream processing.

## Current Agent / Collection Direction

The recent backend changes also introduced a more real-time collection direction:

- Media stream: WebSocket at `/api/practice/stream`
- Current frontend media format: WebM chunks from `MediaRecorder`
- Environment includes `GOOGLE_API_KEY` support for Gemini-based multimodal workflows
- LangChain and Gemini packages are now part of backend dependencies

This means the backend is evolving beyond a simple “upload frame, get result” design and toward a live session pipeline.

## What The Frame Processor Does

The frame processor is intentionally narrow right now. It only handles the early filtering pipeline.

Processing order:

1. Decode the incoming image
2. Run person detection
3. If a person is detected, drop the frame immediately
4. Compare the frame against the last accepted frame using a fast grayscale diff
5. If the frame is too similar, drop it
6. Otherwise accept it and store it as the new last accepted frame

This means the backend now has a cheap gatekeeper in front of future heavy tasks like OCR, system extraction, or evaluation.

## What Is Implemented In The Frame Processor

- Accepts image input as base64, bytes, or a NumPy array
- Uses OpenCV to decode images
- Uses YOLOv8 nano through `ultralytics` for person detection
- Only checks for the `person` class
- Uses grayscale + resize + mean absolute difference for fast similarity checks
- Compares new frames only against the last accepted frame
- Returns `None` for discarded frames
- Returns a minimal payload with `timestamp` and encoded image bytes for accepted frames

## What Is Not Implemented Yet

- OCR
- Whiteboard structure extraction
- Architecture understanding from filtered frames
- Graph creation directly from visual input
- External API calls from the frame filter itself

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

The packaging config in `backend/pyproject.toml` was also updated so editable installs work with the current multi-package backend layout.

## Recommended Next Backend Steps

- Connect `FrameProcessor.process_frame(...)` to a real backend entrypoint if we still want a filtered-frame path
- Decide whether the new live media stream fully replaces periodic image-frame ingestion
- Add tests for base64 decode, diff threshold behavior, last accepted frame state behavior, and the person-detected discard path
- Decide where YOLO weights should be cached in local and deployed environments
- Decide whether accepted images should stay as raw bytes or be normalized to one standard format across the pipeline

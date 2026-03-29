# Backend

This backend contains two main responsibilities:

- A Python HTTP server (Starlette + Uvicorn) for live system-design sessions
- A visual-delta pipeline that converts accepted frames into text updates for the agent

## Current Layout

```text
backend/
  agent/
    agent.py             # LangChain + Gemini agent that consumes visual_delta text
  core/
    frame_processor.py   # Early frame filtering: decode -> person detect -> diff
    visual_delta_pipeline.py  # OCR + connection detection + visual_delta generation
    graph.py             # In-memory system design graph
    session_store.py     # MongoDB persistence for finished sessions
  server/
    app.py               # Starlette HTTP server + all endpoints
  docs/
    api-reference.md
    flow-and-examples.md
  main.py                # Server entrypoint (uv run main.py)
  pyproject.toml         # Python dependencies and packaging config
```

## What The Backend Does Today

### 1. HTTP session backend

The server starts from `backend/main.py` and runs the Starlette app in `backend/server/app.py`.

That server:

- keeps one in-memory graph + agent per active session
- exposes HTTP endpoints for session management
- accepts `POST /agent/process-capture` (JPEG frames from the frontend)
- runs the visual-delta pipeline on each accepted frame
- calls the Gemini agent with the resulting text description
- accepts `POST /end-session` and writes the finished session to MongoDB

### 2. Visual-delta pipeline

The visual-delta pipeline lives in `backend/core/visual_delta_pipeline.py`.

Its job is to turn live frames into plain-English structural updates before the
agent touches them.

It follows this order:

1. Decode image input
2. Run person detection
3. If a person is found, discard the frame
4. Compare against the last accepted frame using grayscale MAD diff
5. If too similar, discard the frame
6. Run OCR on the accepted frame with local `tesseract`
7. Extract components, nearby annotation text, and simple connections
8. Compare the OCR snapshot to the previous accepted OCR snapshot
9. Generate a plain-text `visual_delta` string
10. Pass that `visual_delta` to the agent for graph mutations

This means the agent no longer receives raw images directly. It receives a
plain-English description of the visual change instead.

## Visual Delta Output

The pipeline generates text like:

```text
A box labeled 'Redis Cache' was drawn with an arrow from 'API Service'.
Text '3 replicas' was added near 'API Service'.
An arrow was drawn from 'Browser' to 'API'.
```

## Frame Processor API

```python
from core.frame_processor import FrameProcessor

processor = FrameProcessor()
result = processor.process_frame(image_payload, timestamp=123.45)
```

Accepted output:

```python
{
    "timestamp": 123.45,
    "image": b"...encoded image bytes..."
}
```

Discarded output:

```python
None
```

## Install

Use [uv](https://docs.astral.sh/uv/) to install dependencies:

```bash
cd backend
uv sync
```

This creates `backend/.venv` automatically.

## Run

```bash
cd backend
uv run main.py
```

Make sure `.env` at the repo root contains valid `MONGODB_URI` and `GOOGLE_API_KEY` values before starting. See `.env.example` for the template.

## Dependencies Used By The Visual Pipeline

- `numpy`
- `opencv-python`
- `ultralytics`
- local `tesseract` binary

These are used for image decoding, resizing, diffing, person detection, OCR,
and simple visual-structure extraction.

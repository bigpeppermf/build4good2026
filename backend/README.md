# Backend

This backend currently contains two main responsibilities:

- A Python MCP server for live system-design sessions
- A frame-processing gatekeeper that filters images before expensive downstream analysis

## Current Layout

```text
backend/
  core/
    frame_processor.py   # Early frame filtering: decode -> person detect -> diff
    graph.py             # In-memory system design graph
    session_store.py     # MongoDB persistence for finished sessions
  docs/
    api-reference.md
    flow-and-examples.md
  graph_mcp/
    server.py            # MCP server and /end-session route
  main.py                # Server entrypoint
  pyproject.toml         # Python dependencies and packaging config
```

## What The Backend Does Today

### 1. MCP graph backend

The current server starts from `backend/main.py` and runs the MCP app in `backend/graph_mcp/server.py`.

That server:

- keeps one in-memory graph for the active session
- exposes MCP tools for AI-driven graph edits
- accepts `POST /end-session`
- writes the finished session to MongoDB

### 2. Frame gatekeeper

The frame gatekeeper lives in `backend/core/frame_processor.py`.

Its job is to cheaply reject frames before they reach future expensive steps.

It follows this order:

1. Decode image input
2. Run person detection
3. If a person is found, discard the frame
4. Compare against the last accepted frame using grayscale MAD diff
5. If too similar, discard the frame
6. Otherwise return the accepted frame and update internal state

This module does not do OCR, system extraction, or graph logic.

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

Create a virtual environment and install the backend in editable mode:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e backend
```

If you need to activate it in your shell:

```bash
source backend/.venv/bin/activate
```

## Run

The current backend server entrypoint is:

```bash
python backend/main.py
```

Before running the MCP server, make sure `.env` contains a valid `MONGODB_URI`.

## Dependencies Added For Frame Processing

- `numpy`
- `opencv-python`
- `ultralytics`

These are used for image decoding, resizing, diffing, and lightweight person detection.

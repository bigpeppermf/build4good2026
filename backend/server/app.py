"""
HTTP server for the real-time system design graph backend.

Endpoints:
  GET  /docs                    — API reference rendered as HTML
  POST /new-session             — create an isolated graph + agent + CV pipeline for a user
  POST /agent/process-frame   — send a visual_delta (JSON) to the Gemini agent
  POST /agent/process-capture — multipart JPEG + session_id; runs Gemini Vision pipeline then agent
  POST /end-session           — save the completed graph to MongoDB

Run:
    uv run main.py
"""

import os
import uuid
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from agent import WhiteboardAgent
from core.graph import SystemDesignGraph
from core.session_store import SessionStore

load_dotenv()

# ------------------------------------------------------------------ #
# Shared state                                                         #
# ------------------------------------------------------------------ #

_store = SessionStore(uri=os.environ["MONGODB_URI"])

# Per-user session registry: session_id → {"graph": ..., "agent": ...}
_sessions: dict[str, dict] = {}


# ------------------------------------------------------------------ #
# Endpoints                                                            #
# ------------------------------------------------------------------ #

async def serve_docs(_request: Request) -> HTMLResponse:
    """
    GET /docs
    Renders the API reference markdown as an HTML page in the browser.
    """
    docs_path = Path(__file__).parent.parent / "docs" / "api-reference.md"
    markdown = docs_path.read_text(encoding="utf-8")
    # Escape backticks so the JS template literal stays valid
    escaped = markdown.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>System Design Graph — API Reference</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 2rem 1rem;
      background: #0a0d0b;
      color: #d8e4d8;
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 0.9375rem;
      line-height: 1.65;
    }}
    #content {{ max-width: 860px; margin: 0 auto; }}
    h1, h2, h3 {{ color: #e8f0e8; letter-spacing: -0.02em; }}
    h1 {{ font-size: 1.75rem; border-bottom: 1px solid #2a3a2a; padding-bottom: .5rem; }}
    h2 {{ font-size: 1.2rem; margin-top: 2.5rem; border-bottom: 1px solid #1e2e1e; padding-bottom: .25rem; }}
    h3 {{ font-size: 1rem; color: #a8c4a8; }}
    a {{ color: #6b9f6b; }}
    code {{
      font-family: "IBM Plex Mono", "Fira Mono", monospace;
      font-size: 0.825rem;
      background: #141e14;
      border: 1px solid #2a3a2a;
      border-radius: 3px;
      padding: .1em .35em;
    }}
    pre {{
      background: #0e160e;
      border: 1px solid #2a3a2a;
      border-radius: 4px;
      padding: 1rem;
      overflow-x: auto;
    }}
    pre code {{ background: none; border: none; padding: 0; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 0.875rem;
      margin: 1rem 0;
    }}
    th, td {{
      text-align: left;
      padding: .45rem .75rem;
      border: 1px solid #2a3a2a;
    }}
    th {{ background: #141e14; color: #a8c4a8; font-weight: 600; }}
    tr:nth-child(even) {{ background: #0e160e; }}
    blockquote {{
      margin: 0;
      padding: .5rem 1rem;
      border-left: 3px solid #3a5a3a;
      color: #90a890;
    }}
  </style>
</head>
<body>
  <div id="content"></div>
  <script>
    const md = `{escaped}`;
    document.getElementById("content").innerHTML = marked.parse(md);
  </script>
</body>
</html>"""
    return HTMLResponse(html)


async def new_session(_request: Request) -> JSONResponse:
    """
    POST /new-session
    Creates a fresh graph and agent for a new user session.
    Returns a session_id that must be included in all subsequent requests.

    The ``VisualDeltaPipeline`` (YOLO + Gemini Vision) is created lazily on
    the first ``POST /agent/process-capture`` so importing this module does
    not load heavyweight CV dependencies.
    """
    session_id = str(uuid.uuid4())
    graph = SystemDesignGraph()
    agent = WhiteboardAgent(graph)
    _sessions[session_id] = {"graph": graph, "agent": agent}
    return JSONResponse({"session_id": session_id})


async def process_frame(request: Request) -> JSONResponse:
    """
    POST /agent/process-frame
    Called by the computer vision pipeline after each whiteboard frame is
    analysed.  Passes the text description of what changed to the Gemini agent,
    which calls graph mutation tools as needed and returns a one-sentence verbal
    response.

    JSON body:
        session_id    — ID returned by POST /new-session
        visual_delta  — text description of what changed on the whiteboard
        timestamp_ms  — milliseconds since session start (default: 0)
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)

    session_id = body.get("session_id", "")
    if not session_id or session_id not in _sessions:
        return JSONResponse({"error": "Invalid or missing 'session_id'."}, status_code=404)

    visual_delta = body.get("visual_delta", "")
    timestamp_ms = int(body.get("timestamp_ms", 0))

    if not isinstance(visual_delta, str) or not visual_delta.strip():
        return JSONResponse({"error": "Missing or empty 'visual_delta' field."}, status_code=400)

    try:
        verbal_response = _sessions[session_id]["agent"].process_frame(visual_delta, timestamp_ms)
        return JSONResponse({"verbal_response": verbal_response, "timestamp_ms": timestamp_ms})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)


async def end_session(request: Request) -> JSONResponse:
    """
    POST /end-session
    Called by the frontend when the user finishes their design.
    Saves the session graph to MongoDB, removes it from the registry,
    and returns a summary.

    JSON body:
        session_id — ID returned by POST /new-session
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)

    session_id = body.get("session_id", "")
    if not session_id or session_id not in _sessions:
        return JSONResponse({"error": "Invalid or missing 'session_id'."}, status_code=404)

    graph = _sessions[session_id]["graph"]
    if len(graph) == 0:
        return JSONResponse({"error": "Graph is empty — nothing to save."}, status_code=400)

    # Pop before saving so the session is always cleaned up from memory,
    # even if the MongoDB write fails.
    _sessions.pop(session_id)

    try:
        summary = await _store.save_session(graph, session_id)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"Failed to save session: {exc}"}, status_code=500)

    return JSONResponse({"status": "saved", **summary})


def _pipeline_error_message(exc: BaseException) -> str:
    """Turn low-level import/CV failures into actionable text for the browser."""
    raw = str(exc)
    low = raw.lower()
    if isinstance(exc, ImportError):
        return (
            "CV dependencies failed to import. In the backend folder run: "
            "uv sync && uv run main.py"
        )
    if "numpy" in low and (
        "not available" in low or "no module named" in low or "failed" in low
    ):
        return (
            "NumPy/OpenCV could not load in this Python environment. "
            "Run the API from the backend folder with: uv sync && uv run main.py"
        )
    return raw


async def process_capture(request: Request) -> JSONResponse:
    """
    POST /agent/process-capture
    Multipart body for the browser / CV path: JPEG frame + session_id + timestamp.
    Runs the per-session visual_delta pipeline, then the Gemini agent when a delta
    is produced (same as POST /agent/process-frame with plain-text visual_delta).
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "Could not parse form body."}, status_code=400)

    raw_sid = form.get("session_id")
    session_id = raw_sid if isinstance(raw_sid, str) else ""
    if not session_id or session_id not in _sessions:
        return JSONResponse({"error": "Invalid or missing 'session_id'."}, status_code=404)

    raw_ts = form.get("timestamp_ms", "0")
    timestamp_ms = int(raw_ts) if isinstance(raw_ts, str) else 0

    frame_upload = form.get("frame")
    if not isinstance(frame_upload, UploadFile):
        return JSONResponse({"error": "Missing or invalid 'frame' field."}, status_code=400)

    frame_bytes: bytes = await frame_upload.read()
    if not frame_bytes:
        return JSONResponse({"error": "Empty frame."}, status_code=400)

    sess = _sessions[session_id]
    if "pipeline" not in sess:
        from core.visual_delta_pipeline import VisualDeltaPipeline

        sess["pipeline"] = VisualDeltaPipeline()
    pipeline = sess["pipeline"]
    agent = sess["agent"]

    try:
        pipeline_result = pipeline.process_frame(frame_bytes, timestamp_ms)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": _pipeline_error_message(exc)}, status_code=500)

    if pipeline_result is None:
        return JSONResponse({"discarded": True, "timestamp_ms": timestamp_ms})

    try:
        verbal_response = agent.process_frame(
            pipeline_result["visual_delta"],
            timestamp_ms,
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)

    # Persist frame data to MongoDB in the background.
    try:
        await _store.save_frame(
            session_id=session_id,
            timestamp_ms=timestamp_ms,
            visual_delta=pipeline_result["visual_delta"],
            verbal_response=verbal_response,
        )
    except Exception:  # noqa: BLE001
        pass  # Non-critical — don't fail the response if the write fails.

    return JSONResponse(
        {
            "verbal_response": verbal_response,
            "visual_delta": pipeline_result["visual_delta"],
            "timestamp_ms": timestamp_ms,
        }
    )


# ------------------------------------------------------------------ #
# App assembly                                                         #
# ------------------------------------------------------------------ #

app = Starlette(
    routes=[
        Route("/docs", serve_docs, methods=["GET"]),
        Route("/new-session", new_session, methods=["POST"]),
        Route("/agent/process-frame", process_frame, methods=["POST"]),
        Route("/agent/process-capture", process_capture, methods=["POST"]),
        Route("/end-session", end_session, methods=["POST"]),
    ],
)


def serve() -> None:
    print("Docs            : GET  http://localhost:8000/docs")
    print("New session     : POST http://localhost:8000/new-session")
    print("Process frame   : POST http://localhost:8000/agent/process-frame")
    print("Process capture : POST http://localhost:8000/agent/process-capture")
    print("End session     : POST http://localhost:8000/end-session")
    uvicorn.run(app, host="0.0.0.0", port=8000)

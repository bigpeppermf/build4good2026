"""
HTTP server for the real-time system design graph backend.

Endpoints:
  GET  /docs                    — API reference rendered as HTML
  POST /new-session             — create an isolated graph + agent + CV pipeline for a user
  POST /agent/process-frame   — send a visual_delta (JSON) to the Gemini agent
  POST /agent/process-capture — multipart JPEG + session_id; runs Gemini Vision pipeline then agent
  POST /end-session           — save the completed graph to MongoDB
  POST /chat                  — ask follow-up questions using saved analysis context

Run:
    uv run main.py
"""

import asyncio
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

from agent import AnalysisAgent, ChatAgent, ValidationAgent, WhiteboardAgent
from core.graph import SystemDesignGraph
from core.session_store import SessionStore

load_dotenv()

# ------------------------------------------------------------------ #
# Shared state                                                         #
# ------------------------------------------------------------------ #

_store = SessionStore(uri=os.environ["MONGODB_URI"])

# Per-user session registry: session_id → {"graph": ..., "agent": ...}
_sessions: dict[str, dict] = {}
_analysis_jobs: dict[str, dict] = {}


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


async def analysis_status(request: Request) -> JSONResponse:
    """
    GET /analysis/{session_id}
    Poll status for a post-session analysis/save job started by POST /end-session.
    """
    session_id = request.path_params.get("session_id", "")
    if not session_id:
        return JSONResponse({"error": "Missing 'session_id' path parameter."}, status_code=400)

    status_payload = _analysis_jobs.get(session_id)
    if status_payload is None:
        return JSONResponse({"error": "Unknown 'session_id' for analysis."}, status_code=404)

    return JSONResponse(status_payload)


async def _run_post_session_pipeline(
    session_id: str,
    graph: SystemDesignGraph,
    audio_bytes: bytes,
    audio_mime_type: str,
) -> None:
    """
    Post-session pipeline:
    validate graph against audio transcript, persist validated graph, then run
    structured analysis.
    """
    current_stage = "validation"
    validation_result = None
    analysis_output = None
    analysis_save_summary = None
    try:
        _analysis_jobs[session_id] = {
            "session_id": session_id,
            "status": "processing",
            "stage": "validation",
        }

        validator = ValidationAgent(graph)
        validation_result = await validator.validate_audio(audio_bytes, audio_mime_type)

        current_stage = "saving_session"
        _analysis_jobs[session_id] = {
            "session_id": session_id,
            "status": "processing",
            "stage": "saving_session",
            "validation_summary": validation_result.validation_summary,
            "validation_corrections": validation_result.corrections_made,
            "graph_confidence": validation_result.graph_confidence,
        }

        summary = await _store.save_session(
            graph,
            session_id,
            audio_transcript=validation_result.transcript,
            validation_corrections=validation_result.corrections_made,
            validation_summary=validation_result.validation_summary,
            graph_confidence=validation_result.graph_confidence,
        )

        current_stage = "analysis"
        _analysis_jobs[session_id] = {
            "session_id": session_id,
            "status": "processing",
            "stage": "analysis",
            "validation_summary": validation_result.validation_summary,
            "validation_corrections": validation_result.corrections_made,
            "graph_confidence": validation_result.graph_confidence,
        }

        session_metadata = {
            "session_id": session_id,
            "duration_ms": 0,
            "frames_processed": 0,
            "agent_responses": 0,
            "nodes_saved": summary.get("nodes_saved", 0),
            "edges_saved": summary.get("edges_saved", 0),
        }
        analyzer = AnalysisAgent()
        analysis_output = analyzer.analyze(
            graph=graph,
            transcript=validation_result.transcript,
            session_metadata=session_metadata,
        )

        current_stage = "saving_analysis"
        _analysis_jobs[session_id] = {
            "session_id": session_id,
            "status": "processing",
            "stage": "saving_analysis",
            "validation_summary": validation_result.validation_summary,
            "validation_corrections": validation_result.corrections_made,
            "graph_confidence": validation_result.graph_confidence,
        }
        analysis_save_summary = await _store.save_analysis(session_id, analysis_output)

        _analysis_jobs[session_id] = {
            "session_id": session_id,
            "status": "complete",
            "stage": "complete",
            "session_summary": summary,
            "analysis_summary": analysis_save_summary if analysis_save_summary else {},
            "analysis": analysis_output["analysis"] if analysis_output else {},
            "feedback": analysis_output["feedback"] if analysis_output else {},
            "score": analysis_output["score"] if analysis_output else {},
            "validation_summary": (
                validation_result.validation_summary
                if validation_result is not None
                else "Graph matches transcript"
            ),
            "validation_corrections": (
                validation_result.corrections_made
                if validation_result is not None
                else 0
            ),
            "graph_confidence": (
                validation_result.graph_confidence
                if validation_result is not None
                else 1.0
            ),
        }
    except Exception as exc:  # noqa: BLE001
        _analysis_jobs[session_id] = {
            "session_id": session_id,
            "status": "failed",
            "stage": current_stage,
            "error": f"Post-session pipeline failed: {exc}",
        }


async def end_session(request: Request) -> JSONResponse:
    """
    POST /end-session
    Called by the frontend when the user finishes their design.
    Accepts multipart/form-data:
      session_id - ID returned by POST /new-session
      audio      - recorded session audio blob (webm/ogg)
    Returns HTTP 202 and starts asynchronous post-session processing.
    """
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return JSONResponse(
            {"error": "Content-Type must be multipart/form-data."},
            status_code=400,
        )

    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "Could not parse form body."}, status_code=400)

    raw_sid = form.get("session_id")
    session_id = raw_sid if isinstance(raw_sid, str) else ""
    if not session_id or session_id not in _sessions:
        return JSONResponse({"error": "Invalid or missing 'session_id'."}, status_code=404)

    audio_upload = form.get("audio")
    if not isinstance(audio_upload, UploadFile):
        return JSONResponse({"error": "Missing or invalid 'audio' field."}, status_code=400)

    audio_bytes: bytes = await audio_upload.read()
    if not audio_bytes:
        return JSONResponse({"error": "Empty audio upload."}, status_code=400)
    audio_mime_type = audio_upload.content_type or "audio/webm"

    graph = _sessions[session_id]["graph"]
    if len(graph) == 0:
        return JSONResponse({"error": "Graph is empty - nothing to save."}, status_code=400)

    # Pop before enqueueing so IDs are not reusable while processing.
    _sessions.pop(session_id)
    _analysis_jobs[session_id] = {
        "session_id": session_id,
        "status": "processing",
        "stage": "queued",
    }

    try:
        asyncio.create_task(
            _run_post_session_pipeline(
                session_id,
                graph,
                audio_bytes,
                audio_mime_type,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _analysis_jobs[session_id] = {
            "session_id": session_id,
            "status": "failed",
            "stage": "queued",
            "error": f"Failed to start post-session processing: {exc}",
        }
        return JSONResponse({"error": f"Failed to start post-session processing: {exc}"}, status_code=500)

    return JSONResponse(
        {"session_id": session_id, "status": "processing"},
        status_code=202,
    )


async def chat(request: Request) -> JSONResponse:
    """
    POST /chat
    JSON body:
      session_id - completed session ID with saved analysis
      message    - user follow-up question
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)

    raw_sid = body.get("session_id") if isinstance(body, dict) else None
    session_id = raw_sid.strip() if isinstance(raw_sid, str) else ""
    if not session_id:
        return JSONResponse({"error": "Missing or invalid 'session_id'."}, status_code=400)

    raw_message = body.get("message") if isinstance(body, dict) else None
    message = raw_message.strip() if isinstance(raw_message, str) else ""
    if not message:
        return JSONResponse({"error": "Missing or empty 'message'."}, status_code=400)

    analysis_doc = await _store.get_analysis(session_id)
    if analysis_doc is None:
        return JSONResponse({"error": "Unknown 'session_id' for chat."}, status_code=404)

    seed_context_raw = analysis_doc.get("chat_seed_context")
    seed_context = seed_context_raw.strip() if isinstance(seed_context_raw, str) else ""
    if not seed_context:
        return JSONResponse({"error": "Chat context is unavailable for this session."}, status_code=404)

    try:
        agent = ChatAgent(chat_seed_context=seed_context)
        response_text = agent.respond(message)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"Chat failed: {exc}"}, status_code=500)

    return JSONResponse(
        {
            "session_id": session_id,
            "response": response_text,
        }
    )


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
        Route("/analysis/{session_id}", analysis_status, methods=["GET"]),
        Route("/chat", chat, methods=["POST"]),
        Route("/agent/process-frame", process_frame, methods=["POST"]),
        Route("/agent/process-capture", process_capture, methods=["POST"]),
        Route("/end-session", end_session, methods=["POST"]),
    ],
)


def serve() -> None:
    print("Docs            : GET  http://localhost:8000/docs")
    print("New session     : POST http://localhost:8000/new-session")
    print("Analysis status : GET  http://localhost:8000/analysis/{session_id}")
    print("Chat            : POST http://localhost:8000/chat")
    print("Process frame   : POST http://localhost:8000/agent/process-frame")
    print("Process capture : POST http://localhost:8000/agent/process-capture")
    print("End session     : POST http://localhost:8000/end-session")
    uvicorn.run(app, host="0.0.0.0", port=8000)

"""
MCP server for real-time system design graph mutation.

MCP tools (AI-callable via /mcp):
  - createNode           — register a new component
  - addDetailsToNode     — annotate an existing component
  - deleteNode           — remove a component and its edges
  - addEdge              — connect two components
  - removeEdge           — disconnect two components
  - setEntryPoint        — designate the BFS traversal root
  - insertNodeBetween    — atomically insert a node between two connected nodes
  - getGraphState        — inspect current graph (nodes + edges)

HTTP endpoints (frontend-callable, not AI tools):
  POST /agent/process-frame  — send a JPEG frame to the Gemini agent for analysis
  POST /end-session          — saves the completed graph to MongoDB

Run:
    uv run main.py
"""

import os
import uuid
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from agent import WhiteboardAgent
from core.graph import SystemDesignGraph
from core.session_store import SessionStore

load_dotenv()

# ------------------------------------------------------------------ #
# Shared state                                                         #
# ------------------------------------------------------------------ #

# _graph is used exclusively by the MCP tools at /mcp.
# HTTP callers (CV pipeline, frontend) use _sessions below.
_graph = SystemDesignGraph()
_store = SessionStore(uri=os.environ["MONGODB_URI"])

# Per-user session registry: session_id → {"graph": ..., "agent": ...}
_sessions: dict[str, dict] = {}

# ------------------------------------------------------------------ #
# MCP server + tools                                                   #
# ------------------------------------------------------------------ #

mcp = FastMCP("SystemDesignGraph")


@mcp.tool()
def createNode(id: str, label: str, type: str) -> dict:
    """
    Register a new system component on the graph.

    Args:
        id:    Unique identifier for this node (e.g. 'api_gateway').
        label: Human-readable name shown on the whiteboard (e.g. 'API Gateway').
        type:  Component category — e.g. 'service', 'database', 'cache',
               'load_balancer', 'queue', 'client', 'storage', 'external'.
    """
    node = _graph.create_node(id=id, label=label, type=type)
    return {"status": "created", "node": {"id": node.id, "label": node.label, "type": node.type}}


@mcp.tool()
def addDetailsToNode(id: str, details: dict) -> dict:
    """
    Add or update descriptive details on an existing node.

    Args:
        id:      ID of the node to annotate.
        details: Key-value pairs of additional information
                 (e.g. {"technology": "PostgreSQL", "role": "primary write store"}).
    """
    node = _graph.add_details_to_node(id=id, details=details)
    return {"status": "updated", "node": {"id": node.id, "details": node.details}}


@mcp.tool()
def deleteNode(id: str) -> dict:
    """
    Remove a component and all edges connected to it.

    Args:
        id: ID of the node to delete.
    """
    _graph.delete_node(id=id)
    return {"status": "deleted", "id": id}


@mcp.tool()
def addEdge(fromId: str, toId: str, label: str = "") -> dict:
    """
    Draw a directed connection between two components.

    Args:
        fromId: Source node ID.
        toId:   Destination node ID.
        label:  Optional description of the relationship
                (e.g. 'routes traffic to', 'writes to', 'publishes events').
    """
    edge = _graph.add_edge(from_id=fromId, to_id=toId, label=label)
    return {"status": "added", "edge": {"from": edge.from_id, "to": edge.to_id, "label": edge.label}}


@mcp.tool()
def removeEdge(fromId: str, toId: str) -> dict:
    """
    Remove the directed connection from one component to another.

    Args:
        fromId: Source node ID.
        toId:   Destination node ID.
    """
    _graph.remove_edge(from_id=fromId, to_id=toId)
    return {"status": "removed", "from": fromId, "to": toId}


@mcp.tool()
def setEntryPoint(id: str) -> dict:
    """
    Designate the logical entry point of the system design.
    BFS traversal — and therefore MongoDB traversal_index — starts from this node.

    Call this as soon as you identify the user-facing start of the design
    (e.g. 'Client Browser', 'Mobile App', 'CDN'). If the user drew components
    out of logical order, call this to correct the traversal root.

    Args:
        id: ID of the node that represents the entry point of the system.
    """
    _graph.set_entry_point(id=id)
    return {"status": "entry_point_set", "entry_point": id}


@mcp.tool()
def insertNodeBetween(
    fromId: str,
    newId: str,
    newLabel: str,
    newType: str,
    toId: str,
    fromLabel: str = "",
    toLabel: str = "",
) -> dict:
    """
    Insert a new node between two already-connected nodes.

    Use this when the user introduces a component that belongs logically
    between two things that are already directly connected.

    Example: Frontend ──▶ Database exists, user says "actually there's an
    API between them" → insertNodeBetween("frontend", "api", "API", "service", "database")
    Result:  Frontend ──▶ API ──▶ Database  (old direct edge is removed)

    Before calling, verify the direct edge exists via getGraphState().

    Args:
        fromId:    ID of the upstream node (the one sending traffic/data).
        newId:     Unique ID for the new node being inserted.
        newLabel:  Human-readable label for the new node.
        newType:   Component type for the new node.
        toId:      ID of the downstream node (the one receiving traffic/data).
        fromLabel: Optional label for the new upstream edge (fromId → newId).
        toLabel:   Optional label for the new downstream edge (newId → toId).
    """
    node = _graph.insert_node_between(
        from_id=fromId,
        new_id=newId,
        new_label=newLabel,
        new_type=newType,
        to_id=toId,
        from_label=fromLabel,
        to_label=toLabel,
    )
    return {
        "status": "inserted",
        "node": {"id": node.id, "label": node.label, "type": node.type},
        "edges_created": [
            {"from": fromId, "to": newId, "label": fromLabel},
            {"from": newId, "to": toId, "label": toLabel},
        ],
    }


@mcp.tool()
def getGraphState() -> dict:
    """
    Return the full current state of the graph (all nodes and edges).
    Useful for the AI to verify its understanding of the design so far.
    """
    return _graph.get_state()


# ------------------------------------------------------------------ #
# HTTP endpoints (not MCP tools)                                       #
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

    summary = await _store.save_session(graph, session_id)
    _sessions.pop(session_id)
    return JSONResponse({"status": "saved", **summary})


# ------------------------------------------------------------------ #
# App assembly                                                         #
# ------------------------------------------------------------------ #

app = mcp.http_app()
app.add_route("/docs", serve_docs, methods=["GET"])
app.add_route("/new-session", new_session, methods=["POST"])
app.add_route("/agent/process-frame", process_frame, methods=["POST"])
app.add_route("/end-session", end_session, methods=["POST"])


def serve() -> None:
    print("Docs         : GET  http://localhost:8000/docs")
    print("MCP          : http://localhost:8000/mcp")
    print("New session  : POST http://localhost:8000/new-session")
    print("Process frame: POST http://localhost:8000/agent/process-frame")
    print("End session  : POST http://localhost:8000/end-session")
    uvicorn.run(app, host="0.0.0.0", port=8000)

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

import uvicorn
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse

from agent import WhiteboardAgent
from core.graph import SystemDesignGraph
from core.session_store import SessionStore

load_dotenv()

# ------------------------------------------------------------------ #
# Shared state                                                         #
# ------------------------------------------------------------------ #

_graph = SystemDesignGraph()
_session_id = str(uuid.uuid4())
_store = SessionStore(uri=os.environ["MONGODB_URI"])

# One agent instance per server process — persists conversation history
# across frames for the lifetime of the session.
_agent = WhiteboardAgent(_graph)

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

async def process_frame(request: Request) -> JSONResponse:
    """
    POST /agent/process-frame
    Called by the frontend each time a motion-triggered JPEG is captured.
    Passes the frame to the Gemini vision agent which calls graph mutation
    tools as needed and returns a one-sentence verbal response.

    Form fields:
        frame        — JPEG file (binary)
        timestamp_ms — milliseconds since session start (integer string)
    """
    try:
        form = await request.form()
        frame_upload = form.get("frame")
        raw_ts = form.get("timestamp_ms", "0")
        timestamp_ms = int(raw_ts) if isinstance(raw_ts, str) else 0

        if not isinstance(frame_upload, UploadFile):
            return JSONResponse({"error": "Missing or invalid 'frame' field."}, status_code=400)

        frame_bytes: bytes = await frame_upload.read()
        if not frame_bytes:
            return JSONResponse({"error": "Empty frame."}, status_code=400)

        verbal_response = _agent.process_frame(frame_bytes, timestamp_ms)
        return JSONResponse({"verbal_response": verbal_response, "timestamp_ms": timestamp_ms})

    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)


async def end_session(_request: Request) -> JSONResponse:
    """
    POST /end-session
    Called by the frontend when the user finishes their design.
    Saves the current graph to MongoDB and returns a summary.
    """
    if len(_graph) == 0:
        return JSONResponse({"error": "Graph is empty — nothing to save."}, status_code=400)

    summary = await _store.save_session(_graph, _session_id)
    return JSONResponse({"status": "saved", **summary})


# ------------------------------------------------------------------ #
# App assembly                                                         #
# ------------------------------------------------------------------ #

app = mcp.http_app()
app.add_route("/agent/process-frame", process_frame, methods=["POST"])
app.add_route("/end-session", end_session, methods=["POST"])


def serve() -> None:
    print(f"Session ID   : {_session_id}")
    print("MCP          : http://localhost:8000/mcp")
    print("Process frame: POST http://localhost:8000/agent/process-frame")
    print("End session  : POST http://localhost:8000/end-session")
    uvicorn.run(app, host="0.0.0.0", port=8000)

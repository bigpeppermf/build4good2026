# API Reference

Complete reference for all MCP tools, HTTP endpoints, and core classes in the system design backend.

---

## Overview

This backend supports a real-time system design analysis tool. A user draws components on a whiteboard — a separate computer vision pipeline analyzes JPEG frames and sends text descriptions of changes to the Gemini agent, which builds a graph of the design as it unfolds. **The agent never receives raw images or audio; it receives only text descriptions produced by the CV pipeline.** When the session ends, the graph is persisted to MongoDB for scoring and comparison.

### Three surfaces, two callers

| Surface | Caller | Purpose |
|---------|--------|---------|
| MCP tools (`/mcp`) | External MCP clients | Mutate and inspect the graph via the MCP protocol |
| `POST /agent/process-frame` | CV pipeline | Send a text description of whiteboard changes to the Gemini agent |
| `POST /end-session` | Frontend | Persist the completed graph to MongoDB |

### Tool categories

| Category | Tools | When used |
|----------|-------|-----------|
| **Create** | `createNode`, `addEdge` | New component or connection introduced |
| **Annotate** | `addDetailsToNode` | User provides more info about an existing component |
| **Remove** | `deleteNode`, `removeEdge` | User erases or redirects something |
| **Structure** | `setEntryPoint`, `insertNodeBetween` | Logical ordering and mid-stream corrections |
| **Inspect** | `getGraphState` | AI fact-checks topology before structural changes |

### Project layout

```
backend/
  agent/
    __init__.py       # Exports WhiteboardAgent
    agent.py          # LangChain + Gemini agent with graph tools
  core/
    graph.py          # SystemDesignGraph — in-memory graph data structure
    session_store.py  # SessionStore — MongoDB write logic
    frame_processor.py# FrameProcessor — CV frame filtering (standalone)
  server/
    app.py            # Starlette HTTP server + all endpoints
  main.py             # Entry point
  .env                # MONGODB_URI + GOOGLE_API_KEY (not committed)
```

### Running the server

```bash
# Fill in .env first:
# MONGODB_URI=mongodb+srv://<user>:<pass>@benji-cluster.hgust9k.mongodb.net/...
# GOOGLE_API_KEY=your_google_api_key_here

uv run main.py
# Session ID   : <uuid>
# MCP          : http://localhost:8000/mcp
# Process frame: POST http://localhost:8000/agent/process-frame
# End session  : POST http://localhost:8000/end-session
```

---

## MCP Tools

MCP tools are functions the AI agent calls directly over the MCP protocol at `http://localhost:8000/mcp`. They are **not** callable by the frontend — only by the AI.

All tools return a JSON dict. On error, they raise a `ValueError` which FastMCP converts to an error response.

---

### `createNode`

Register a new system component on the graph.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | Yes | Unique identifier used to reference this node in all other calls. Use snake_case (e.g. `api_gateway`, `postgres_db`). |
| `label` | `str` | Yes | Human-readable display name shown on the whiteboard (e.g. `API Gateway`). |
| `type` | `str` | Yes | Component category. See valid types below. |

**Valid `type` values**

| Type | Description |
|------|-------------|
| `client` | User-facing entry point (browser, mobile app) |
| `service` | Application service or API |
| `load_balancer` | Traffic distribution layer |
| `cache` | In-memory caching layer (Redis, Memcached) |
| `database` | Persistent data store |
| `queue` | Message broker or event bus (Kafka, RabbitMQ) |
| `storage` | Object/file storage (S3, GCS) |
| `external` | Third-party service outside the system boundary |

**Returns**
```json
{
  "status": "created",
  "node": {
    "id": "api_gateway",
    "label": "API Gateway",
    "type": "service"
  }
}
```

**Errors**
- `ValueError: Node 'api_gateway' already exists.` — ID collision. Use a different ID or call `deleteNode` first.

---

### `addDetailsToNode`

Add or update descriptive details on an existing node. Details are merged — calling this multiple times accumulates information rather than replacing it.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | Yes | ID of the node to annotate. |
| `details` | `dict` | Yes | Key-value pairs of additional information. Keys and values are freeform strings. |

**Common detail keys**

| Key | Example value |
|-----|---------------|
| `technology` | `"PostgreSQL 15"`, `"Redis 7"`, `"NGINX"` |
| `role` | `"primary write store"`, `"read replica"` |
| `scaling` | `"horizontal, 3 replicas"` |
| `replication` | `"async replica in us-east-2"` |
| `protocol` | `"gRPC"`, `"REST"`, `"WebSocket"` |
| `notes` | Any freeform observation |

**Returns**
```json
{
  "status": "updated",
  "node": {
    "id": "postgres_db",
    "details": {
      "technology": "PostgreSQL 15",
      "role": "primary write store"
    }
  }
}
```

**Errors**
- `ValueError: Node 'postgres_db' not found.`

---

### `deleteNode`

Remove a component and all edges incident to it (both incoming and outgoing).

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | Yes | ID of the node to remove. |

**Returns**
```json
{
  "status": "deleted",
  "id": "old_cache"
}
```

**Errors**
- `ValueError: Node 'old_cache' not found.`

**Note:** If the deleted node was the current entry point, the entry point becomes `null`. Call `setEntryPoint` again after deleting the entry node.

---

### `addEdge`

Draw a directed connection from one component to another. Direction represents data or request flow: `fromId` initiates, `toId` receives.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `fromId` | `str` | Yes | ID of the source node (upstream). |
| `toId` | `str` | Yes | ID of the destination node (downstream). |
| `label` | `str` | No | Description of the relationship. Defaults to `""`. |

**Returns**
```json
{
  "status": "added",
  "edge": {
    "from": "load_balancer",
    "to": "api_gateway",
    "label": "routes traffic to"
  }
}
```

**Errors**
- `ValueError: Node 'load_balancer' not found.`
- `ValueError: Edge from 'load_balancer' to 'api_gateway' already exists.`

---

### `removeEdge`

Remove a directed connection between two components. Does not delete the nodes themselves.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `fromId` | `str` | Yes | ID of the source node. |
| `toId` | `str` | Yes | ID of the destination node. |

**Returns**
```json
{
  "status": "removed",
  "from": "api_gateway",
  "to": "postgres_db"
}
```

**Errors**
- `ValueError: No edge from 'api_gateway' to 'postgres_db'.`

---

### `setEntryPoint`

Designate the logical start of the system design. This controls where BFS traversal begins, which determines `traversal_index` values in MongoDB.

Call this as soon as you identify the user-facing entry of the system. If the user described components out of logical order (e.g. drew the backend before mentioning the client), calling this corrects the traversal root without touching any edges.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | Yes | ID of the node that is the logical entry point. Typically a `client` or `load_balancer` type. |

**Returns**
```json
{
  "status": "entry_point_set",
  "entry_point": "client_browser"
}
```

**Errors**
- `ValueError: Node 'client_browser' not found.`

---

### `insertNodeBetween`

Atomically insert a new node between two already-connected nodes. The existing edge is removed and replaced with two new edges through the new node.

**Use when:** the user introduces a component that belongs logically between two things that are already directly connected.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `fromId` | `str` | Yes | ID of the upstream node (sends traffic/data). |
| `newId` | `str` | Yes | Unique ID for the new node. |
| `newLabel` | `str` | Yes | Display label for the new node. |
| `newType` | `str` | Yes | Component type for the new node. |
| `toId` | `str` | Yes | ID of the downstream node (receives traffic/data). |
| `fromLabel` | `str` | No | Label for the new edge `fromId → newId`. Defaults to `""`. |
| `toLabel` | `str` | No | Label for the new edge `newId → toId`. Defaults to `""`. |

**Before (edge must exist):**
```
frontend ──[API calls]──▶ database
```

**After calling `insertNodeBetween("frontend", "api", "API", "service", "database")`:**
```
frontend ──▶ api ──▶ database
```

**Returns**
```json
{
  "status": "inserted",
  "node": { "id": "api", "label": "API", "type": "service" },
  "edges_created": [
    { "from": "frontend", "to": "api", "label": "" },
    { "from": "api", "to": "database", "label": "" }
  ]
}
```

**Errors**
- `ValueError: No edge from 'frontend' to 'database' — cannot insert between them.`
- `ValueError: Node 'api' already exists.`

---

### `getGraphState`

Return a snapshot of the full current graph. Use this to fact-check the topology before making structural decisions.

**Parameters:** None

**Returns**
```json
{
  "entry_point": "client_browser",
  "nodes": [
    { "id": "client_browser", "label": "Client Browser", "type": "client", "details": {} },
    { "id": "api",            "label": "API",            "type": "service", "details": { "technology": "FastAPI" } }
  ],
  "edges": [
    { "from": "client_browser", "to": "api", "label": "HTTP requests" }
  ]
}
```

---

## HTTP Endpoints

HTTP endpoints are called directly by the **frontend**, not via the MCP protocol.

---

### `POST /agent/process-frame`

Called by the **computer vision pipeline** (not the frontend directly) after each whiteboard frame is analyzed. Passes a text description of what structurally changed to the Gemini agent, which calls graph mutation tools as needed and returns a one-sentence verbal response.

**The agent never receives raw images or audio — only the text description.**

**Request:** `application/json`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `visual_delta` | `string` | Yes | Text description of what changed on the whiteboard since the previous frame (e.g. `"A box labeled 'API Gateway' was drawn with an arrow to 'Database'"`). Must be non-empty. |
| `timestamp_ms` | `integer` | No | Milliseconds since session start. Defaults to `0`. |

**Example request**
```json
{
  "visual_delta": "A box labeled 'Load Balancer' appeared above the API service with an arrow pointing down.",
  "timestamp_ms": 4200
}
```

**Response (200)**
```json
{
  "verbal_response": "Got it — I've added the Load Balancer and connected it to the API service.",
  "timestamp_ms": 4200
}
```

**Response (400)**
```json
{ "error": "Missing or empty 'visual_delta' field." }
```

```json
{ "error": "Request body must be JSON." }
```

**Response (500)**
```json
{ "error": "<exception message>" }
```

**Agent behaviour**
- Maintains conversation history across all frames for the session (context persists).
- Calls graph mutation tools (`create_node`, `add_edge`, etc.) when it detects structural changes.
- Returns a Socratic question if two or more consecutive frames show no changes.
- Never fabricates nodes or edges — every mutation is grounded in the visual delta text.

---

### `POST /end-session`

Persist the completed in-memory graph to MongoDB and return a summary. Triggers a BFS traversal to determine node ordering before writing.

**Request body:** None required.

**Response (200)**
```json
{
  "status": "saved",
  "session_id": "ca0504a8-cd51-450b-945e-858cc12b5387",
  "nodes_saved": 5,
  "edges_saved": 4,
  "traversal_order": ["client_browser", "load_balancer", "api", "postgres_db", "redis_cache"]
}
```

**Response (400) — empty graph**
```json
{
  "error": "Graph is empty — nothing to save."
}
```

---

## Core Classes

These live in `core/` and are used internally by the server. They are not directly exposed over HTTP or MCP.

---

### `SystemDesignGraph` (`core/graph.py`)

The in-memory graph. One instance lives for the lifetime of the server process.

| Method | Signature | Description |
|--------|-----------|-------------|
| `create_node` | `(id, label, type) → Node` | Add a new component node |
| `add_details_to_node` | `(id, details) → Node` | Merge details into a node |
| `delete_node` | `(id) → None` | Remove node and all incident edges |
| `add_edge` | `(from_id, to_id, label) → Edge` | Add a directed edge |
| `remove_edge` | `(from_id, to_id) → None` | Remove a directed edge |
| `set_entry_point` | `(id) → None` | Set the BFS root |
| `insert_node_between` | `(from_id, new_id, new_label, new_type, to_id, from_label, to_label) → Node` | Atomic insert between two connected nodes |
| `get_state` | `() → dict` | Full snapshot including entry_point, nodes, edges |
| `bfs_order` | `(start_id?) → list[str]` | Node IDs in BFS traversal order |
| `bfs_serialize` | `(start_id?) → str` | Human-readable BFS document |

---

### `SessionStore` (`core/session_store.py`)

Handles the MongoDB write at session end. Uses Motor (async MongoDB driver).

| Method | Signature | Description |
|--------|-----------|-------------|
| `save_session` | `(graph, session_id) → dict` | Write session + node documents to Atlas |
| `close` | `() → None` | Close the Motor client |

**MongoDB collections written:**

`system_design.sessions`
```json
{
  "_id": "<session_id>",
  "created_at": "<datetime>",
  "traversal_order": ["<node_id>", "..."],
  "edges": [{ "from": "...", "to": "...", "label": "..." }]
}
```

`system_design.nodes`
```json
{
  "session_id": "<session_id>",
  "node_id": "<id>",
  "label": "<label>",
  "type": "<type>",
  "traversal_index": 0,
  "details": {},
  "created_at": "<datetime>"
}
```

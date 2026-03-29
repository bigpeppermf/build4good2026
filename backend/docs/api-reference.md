# API Reference

Complete reference for all graph tools, HTTP endpoints, and core classes in the system design backend.

---

## Overview

This backend supports a real-time system design analysis tool. A user draws components on a whiteboard — the backend filters and OCRs accepted frames, generates a plain-English `visual_delta`, and the Gemini agent uses that text to build a graph of the design. When the session ends, the graph is persisted to MongoDB for scoring and comparison.

### Surfaces

| Surface | Caller | Purpose |
|---------|--------|---------|
| `POST /new-session` | Frontend | Create an isolated graph + agent for a user |
| `POST /agent/process-capture` | Frontend | Upload a raw JPEG frame; backend runs the visual-delta pipeline and calls the agent |
| `POST /agent/process-frame` | CV pipeline (internal) | Send a pre-computed visual_delta text directly to the Gemini agent |
| `POST /end-session` | Frontend | Persist the completed graph to MongoDB |
| `GET /docs` | Browser | View this API reference |

### Graph tool categories

| Category | Tools | When used |
|----------|-------|-----------|
| **Create** | `create_node`, `add_edge` | New component or connection introduced |
| **Annotate** | `add_details_to_node` | User provides more info about an existing component |
| **Remove** | `delete_node`, `remove_edge` | User erases or redirects something |
| **Structure** | `set_entry_point`, `insert_node_between` | Logical ordering and mid-stream corrections |
| **Inspect** | `get_graph_state` | Agent fact-checks topology before structural changes |

### Project layout

```
backend/
  agent/
    __init__.py              # Exports WhiteboardAgent
    agent.py                 # LangChain + Gemini agent that consumes visual_delta text
  core/
    frame_processor.py       # Frame gating: person filter + diff filter
    graph.py                 # SystemDesignGraph — in-memory graph data structure
    session_store.py         # SessionStore — MongoDB write logic
    visual_delta_pipeline.py # OCR + connection detection + visual_delta generation
  server/
    app.py                   # Starlette HTTP server + all endpoints
  main.py                    # Entry point
  .env                       # MONGODB_URI + GOOGLE_API_KEY (not committed)
```

### Running the server

```bash
# Fill in .env first:
# MONGODB_URI=mongodb+srv://<user>:<pass>@benji-cluster.hgust9k.mongodb.net/...
# GOOGLE_API_KEY=your_google_api_key_here

uv run main.py
# Docs         : GET  http://localhost:8000/docs
# New session  : POST http://localhost:8000/new-session
# Process frame: POST http://localhost:8000/agent/process-frame
# End session  : POST http://localhost:8000/end-session
```

### `/agent/process-capture` internal pipeline

When the frontend POSTs a raw JPEG frame to `/agent/process-capture`, the backend runs these steps:

1. Decode the frame
2. Reject if a person is visible
3. Reject if the frame is too similar to the last accepted frame
4. Run OCR on the accepted frame
5. Extract component text, nearby annotation text, and simple connections
6. Compare against the previous accepted OCR snapshot
7. Generate a plain-English `visual_delta`
8. Pass that `visual_delta` to the Gemini agent (same logic as `/agent/process-frame`)

Frames that are rejected return `{ "discarded": true }` immediately.

---

## Graph Tools

These are the LangChain tools available to the Gemini agent. They are called directly in-process — not over HTTP. Each tool mutates the per-session `SystemDesignGraph` and returns a JSON dict. On error, they raise a `ValueError`.

---

### `create_node`

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
- `ValueError: Node 'api_gateway' already exists.`

---

### `add_details_to_node`

Add or update descriptive details on an existing node. Details are merged — calling this multiple times accumulates information rather than replacing it.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | Yes | ID of the node to annotate. |
| `details` | `dict` | Yes | Key-value pairs of additional information. |

**Common detail keys**

| Key | Example value |
|-----|---------------|
| `technology` | `"PostgreSQL 15"`, `"Redis 7"`, `"NGINX"` |
| `role` | `"primary write store"`, `"read replica"` |
| `scaling` | `"horizontal, 3 replicas"` |
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

### `delete_node`

Remove a component and all edges incident to it (both incoming and outgoing).

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | Yes | ID of the node to remove. |

**Returns**
```json
{ "status": "deleted", "id": "old_cache" }
```

**Errors**
- `ValueError: Node 'old_cache' not found.`

---

### `add_edge`

Draw a directed connection from one component to another.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `from_id` | `str` | Yes | ID of the source node (upstream). |
| `to_id` | `str` | Yes | ID of the destination node (downstream). |
| `label` | `str` | No | Description of the relationship. Defaults to `""`. |

**Returns**
```json
{
  "status": "added",
  "edge": { "from": "load_balancer", "to": "api_gateway", "label": "routes traffic to" }
}
```

**Errors**
- `ValueError: Node 'load_balancer' not found.`
- `ValueError: Edge from 'load_balancer' to 'api_gateway' already exists.`

---

### `remove_edge`

Remove a directed connection between two components.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `from_id` | `str` | Yes | ID of the source node. |
| `to_id` | `str` | Yes | ID of the destination node. |

**Returns**
```json
{ "status": "removed", "from": "api_gateway", "to": "postgres_db" }
```

**Errors**
- `ValueError: No edge from 'api_gateway' to 'postgres_db'.`

---

### `set_entry_point`

Designate the logical start of the system design. Controls where BFS traversal begins and determines `traversal_index` values in MongoDB.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | Yes | ID of the entry-point node. Typically a `client` or `load_balancer` type. |

**Returns**
```json
{ "status": "entry_point_set", "entry_point": "client_browser" }
```

**Errors**
- `ValueError: Node 'client_browser' not found.`

---

### `insert_node_between`

Atomically insert a new node between two already-connected nodes. The existing edge is removed and replaced with two new edges through the new node.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `from_id` | `str` | Yes | ID of the upstream node. |
| `new_id` | `str` | Yes | Unique ID for the new node. |
| `new_label` | `str` | Yes | Display label for the new node. |
| `new_type` | `str` | Yes | Component type for the new node. |
| `to_id` | `str` | Yes | ID of the downstream node. |
| `from_label` | `str` | No | Label for the new edge `from_id → new_id`. Defaults to `""`. |
| `to_label` | `str` | No | Label for the new edge `new_id → to_id`. Defaults to `""`. |

**Before:** `frontend ──▶ database`

**After `insert_node_between("frontend", "api", "API", "service", "database")`:** `frontend ──▶ api ──▶ database`

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

### `get_graph_state`

Return a snapshot of the full current graph.

**Parameters:** None

**Returns**
```json
{
  "entry_point": "client_browser",
  "nodes": [
    { "id": "client_browser", "label": "Client Browser", "type": "client", "details": {} },
    { "id": "api", "label": "API", "type": "service", "details": { "technology": "FastAPI" } }
  ],
  "edges": [
    { "from": "client_browser", "to": "api", "label": "HTTP requests" }
  ]
}
```

---

## HTTP Endpoints

---

### `POST /new-session`

Creates a fresh `SystemDesignGraph` and `WhiteboardAgent` for a new user. Returns a `session_id` that must be included in all subsequent requests.

**Request body:** None required.

**Response (200)**
```json
{ "session_id": "f3a1c9d2-4b7e-4f2a-9c3d-1e2b3a4c5d6e" }
```

---

### `POST /agent/process-capture`

Called by the **frontend** every 15 seconds with a raw JPEG still from the camera. The backend runs the full visual-delta pipeline on the frame and, if the frame is accepted, calls the Gemini agent and returns a verbal response.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | `string` | Yes | ID returned by `POST /new-session`. |
| `timestamp_ms` | `integer` (string-encoded) | Yes | Milliseconds since session start. |
| `frame` | file (`image/jpeg`) | Yes | JPEG captured from the camera `<video>` element. |

**Response (200) — frame accepted and processed**
```json
{
  "verbal_response": "Got it — I've added the Load Balancer and connected it to the API service.",
  "visual_delta": "A box labeled 'Load Balancer' was drawn with an arrow to 'API Service'."
}
```

**Response (200) — frame discarded** (person detected or frame too similar to last accepted)
```json
{ "discarded": true }
```

**Response (404)** — unknown session
```json
{ "error": "Invalid or missing 'session_id'." }
```

**Response (500)**
```json
{ "error": "<exception message>" }
```

---

### `POST /agent/process-frame`

Lower-level endpoint used when the `visual_delta` text has already been computed externally (e.g. by a separate CV pipeline). Passes the description directly to the Gemini agent without running any frame processing.

**Request:** `application/json`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | `string` | Yes | ID returned by `POST /new-session`. |
| `visual_delta` | `string` | Yes | Plain-English description of what changed (e.g. `"A box labeled 'API Gateway' was drawn with an arrow to 'Database'"`). Must be non-empty. |
| `timestamp_ms` | `integer` | No | Milliseconds since session start. Defaults to `0`. |

**Example request**
```json
{
  "session_id": "f3a1c9d2-...",
  "visual_delta": "A box labeled 'Load Balancer' appeared with an arrow to 'API Service'.",
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

**Response (400)** — missing/empty `visual_delta`
```json
{ "error": "Missing or empty 'visual_delta' field." }
```

**Response (404)** — unknown session
```json
{ "error": "Invalid or missing 'session_id'." }
```

**Response (500)**
```json
{ "error": "<exception message>" }
```

**Agent behaviour**
- Maintains conversation history across all frames for the session (context persists).
- Calls graph mutation tools when it detects structural changes.
- Never fabricates nodes or edges — every mutation is grounded in the visual_delta text.

---

### `POST /end-session`

Saves the session graph to MongoDB, removes it from the session registry, and returns a summary.

**Request:** `application/json`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | `string` | Yes | ID returned by `POST /new-session`. |

**Response (200)**
```json
{
  "status": "saved",
  "session_id": "f3a1c9d2-...",
  "nodes_saved": 5,
  "edges_saved": 4,
  "traversal_order": ["client_browser", "load_balancer", "api", "postgres_db", "redis_cache"]
}
```

**Response (400)** — empty graph
```json
{ "error": "Graph is empty — nothing to save." }
```

**Response (404)** — unknown session
```json
{ "error": "Invalid or missing 'session_id'." }
```

---

## Core Classes

---

### `SystemDesignGraph` (`core/graph.py`)

In-memory directed graph. One instance per user session.

| Method | Signature | Description |
|--------|-----------|-------------|
| `create_node` | `(id, label, type) → Node` | Add a new component node |
| `add_details_to_node` | `(id, details) → Node` | Merge details into a node |
| `delete_node` | `(id) → None` | Remove node and all incident edges |
| `add_edge` | `(from_id, to_id, label) → Edge` | Add a directed edge |
| `remove_edge` | `(from_id, to_id) → None` | Remove a directed edge |
| `set_entry_point` | `(id) → None` | Set the BFS root |
| `insert_node_between` | `(from_id, new_id, new_label, new_type, to_id, from_label, to_label) → Node` | Atomic insert between two connected nodes |
| `get_state` | `() → dict` | Full snapshot: entry_point, nodes, edges |
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

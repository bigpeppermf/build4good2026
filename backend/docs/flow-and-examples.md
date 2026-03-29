# Flow & Examples

How the system works end-to-end, with worked examples showing how frames become `visual_delta` text and then graph mutations.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  User draws on whiteboard                                           │
│           │                                                         │
│           ▼                                                         │
│  Frame filter + OCR + change describer                              │
│  Receives: JPEG frame                                               │
│  Produces: visual_delta text description                            │
│           │                                                         │
│           ▼  POST /agent/process-capture { session_id, frame JPEG } │
│     WhiteboardAgent (LangChain + Gemini 2.0 Flash)                  │
│     Decides which graph tools to call                               │
│           │                                                         │
│           ▼  direct in-process calls                                │
│  ┌─────────────────────────┐                                        │
│  │  SystemDesignGraph      │                                        │
│  │  (per-session, in RAM)  │                                        │
│  └─────────────────────────┘                                        │
│           │                                                         │
│     Frontend sends POST /end-session { session_id } when done       │
│           │                                                         │
│           ▼                                                         │
│     MongoDB Atlas                                                   │
│     system_design.sessions  (one doc — structure)                   │
│     system_design.nodes     (one doc per component — details)       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The Four Phases

### Phase 1 — Start session

The frontend calls `POST /new-session`. The server creates a fresh `SystemDesignGraph`
and a `WhiteboardAgent` bound to it, stores both under a UUID, and returns the
`session_id`. All subsequent calls include this ID.

### Phase 2 — Live session (in-memory only)

As the user draws, the frontend posts each JPEG frame to `POST /agent/process-capture`. The backend runs the visual-delta pipeline internally before calling the agent:

1. Decode the incoming frame
2. Reject if a person is visible
3. Reject if the frame is too similar to the last accepted frame
4. Run OCR on the accepted frame — extract component labels, annotation text, and simple connections
5. Compare the current OCR snapshot to the previous one
6. Generate a plain-English `visual_delta` (e.g. `"A box labeled 'Redis' was drawn with an arrow from 'API'"`)

The agent receives that `visual_delta` text and runs a tool-call loop with Gemini: it keeps
calling graph tools until Gemini stops requesting them, then returns one sentence spoken
aloud to the user. All graph mutations are instantaneous Python dict operations —
no I/O, no network.

### Phase 3 — BFS + MongoDB write

When the frontend calls `POST /end-session`, the server runs a BFS traversal from
the entry point node to produce `traversal_order`, then writes two MongoDB
collections. The session is removed from memory after saving.

The `SessionStore` makes two writes:
1. One **session document** — the skeleton (edges + traversal order)
2. One **node document per component** — label, type, details, and `traversal_index` in the BFS walk

---

## Decision Tree: what tool does the AI call?

```
New component introduced?
│
├── Is it the user-facing entry (browser, CDN, mobile app)?
│     └── create_node() → set_entry_point()
│
├── Does it belong between two already-connected components?
│     └── get_graph_state() to confirm edge exists
│           └── insert_node_between()
│
├── Does it connect to something at the edge of the current graph?
│     └── create_node() → add_edge()
│
└── Does it add more information to an existing component?
      └── add_details_to_node()

User removes or replaces a component?
│
├── Component removed entirely → delete_node()
└── Connection redirected → remove_edge() → add_edge()

Unsure about current topology before a structural change?
└── get_graph_state() — always call this to fact-check first
```

---

## Example 1 — Simple 3-tier web app

**What the user builds:** Browser → API → PostgreSQL

---

**Frame 1 delta**
```json
{
  "session_id": "abc-123",
  "visual_delta": "A box labeled 'API' was drawn",
  "timestamp_ms": 5000
}
```

Agent tool calls:
```python
create_node("api", "API", "service")
# → {"status": "created", "node": {"id": "api", "label": "API", "type": "service"}}
```

Graph state:
```
api
```

---

**Frame 2 delta**
```json
{
  "session_id": "abc-123",
  "visual_delta": "A box labeled 'PostgreSQL' was drawn with an arrow from 'API'",
  "timestamp_ms": 18000
}
```

Agent tool calls:
```python
create_node("db", "PostgreSQL", "database")
add_edge("api", "db", "writes to")
add_details_to_node("db", {"technology": "PostgreSQL 15"})
```

Graph state:
```
api ──[writes to]──▶ db
```

---

**Frame 3 delta**
```json
{
  "session_id": "abc-123",
  "visual_delta": "A box labeled 'Browser' was drawn with an arrow to 'API'",
  "timestamp_ms": 31000
}
```

Agent tool calls:
```python
create_node("browser", "Client Browser", "client")
add_edge("browser", "api", "HTTP requests")
set_entry_point("browser")
```

Graph state:
```
browser ──[HTTP requests]──▶ api ──[writes to]──▶ db
Entry point: browser
BFS order:  [browser, api, db]
```

Note: `browser` was created third, but `set_entry_point` ensures BFS starts there.

---

**POST /end-session**

MongoDB writes:
```json
// sessions collection
{
  "_id": "abc-123",
  "traversal_order": ["browser", "api", "db"],
  "edges": [
    {"from": "browser", "to": "api", "label": "HTTP requests"},
    {"from": "api",     "to": "db",  "label": "writes to"}
  ]
}

// nodes collection (3 documents)
{"node_id": "browser", "traversal_index": 0, "type": "client",   "details": {}}
{"node_id": "api",     "traversal_index": 1, "type": "service",  "details": {}}
{"node_id": "db",      "traversal_index": 2, "type": "database", "details": {"technology": "PostgreSQL 15"}}
```

---

## Example 2 — Inserting a component between two connected ones

**Scenario:** The user has `browser → api` already in the graph. They draw a load balancer in front of the API.

---

**Frame delta**
```json
{
  "session_id": "abc-123",
  "visual_delta": "A 'Load Balancer' box was drawn between 'Browser' and 'API'",
  "timestamp_ms": 44000
}
```

Agent first fact-checks the current topology:
```python
get_graph_state()
# Returns: edges: [{"from": "browser", "to": "api", "label": "HTTP requests"}]
# Confirms: browser → api edge exists
```

Agent then inserts:
```python
insert_node_between(
    from_id="browser",
    new_id="lb",
    new_label="Load Balancer",
    new_type="load_balancer",
    to_id="api",
    from_label="HTTP requests",
    to_label="routes to",
)
```

What happens internally:
1. Edge `browser → api` is removed
2. Node `lb` is created
3. Edge `browser → lb` is added
4. Edge `lb → api` is added

Graph state after:
```
browser ──[HTTP requests]──▶ lb ──[routes to]──▶ api ──[writes to]──▶ db
BFS order: [browser, lb, api, db]
```

---

## Example 3 — User corrects a mistake

**Scenario:** The user erases the direct API→DB connection and draws a Redis cache in between.

---

**Frame delta**
```json
{
  "session_id": "abc-123",
  "visual_delta": "Arrow from 'API' to 'PostgreSQL' erased, new box 'Redis' drawn with arrows to/from 'API' and 'PostgreSQL'",
  "timestamp_ms": 67000
}
```

Agent tool calls:
```python
remove_edge("api", "db")
create_node("cache", "Redis Cache", "cache")
add_edge("api", "cache", "reads/writes")
add_edge("cache", "db", "cache miss → writes to")
add_details_to_node("cache", {"technology": "Redis 7", "strategy": "write-through"})
```

Graph state after:
```
browser → lb → api → cache → db
                       ↑
                  (Redis 7, write-through)
```

---

## Example 4 — Branching design (fan-out)

**Scenario:** An API that writes to two different stores.

---

**Frame delta**
```json
{
  "session_id": "abc-123",
  "visual_delta": "Two arrows drawn from 'API': one to 'PostgreSQL', one to 'S3'",
  "timestamp_ms": 90000
}
```

Agent tool calls:
```python
create_node("db", "PostgreSQL", "database")
create_node("s3", "S3 Bucket",  "storage")
add_edge("api", "db", "writes user records")
add_edge("api", "s3", "uploads files")
add_details_to_node("db", {"role": "user records"})
add_details_to_node("s3", {"role": "file uploads", "technology": "AWS S3"})
```

Graph state:
```
browser → lb → api ──[writes user records]──▶ db
                   └──[uploads files]────────▶ s3
```

BFS order from `browser`: `[browser, lb, api, db, s3]`

Both `db` and `s3` are at depth 3. BFS visits them in the order their edges were added.

---

## Entry Point Rules

| Situation | What to do |
|-----------|------------|
| User mentions browser, mobile app, CDN first | `create_node` + `set_entry_point` immediately |
| User draws backend components first, then mentions client | `create_node` client node, `set_entry_point`, then connect with `add_edge` |
| Entry point node is deleted | Call `set_entry_point` again on the new logical head |
| Design has no clear single entry (e.g. event-driven) | Set the event source or message broker as entry point |

---

## BFS Traversal and `traversal_index`

`traversal_index` is the position of a node in the BFS walk from the entry point.
It captures the user's conceptual order — from the user-facing layer inward to
the data layer.

```
Entry point: browser (index 0)
  → lb       (index 1)
    → api    (index 2)
      → db   (index 3)
      → s3   (index 4)
```

This index is used for scoring: two users who both built a 5-node design can be
compared node-by-node at the same depth, independent of what they named things
or what order they drew them.

Disconnected nodes (no path from the entry point) receive `traversal_index: -1`
in MongoDB.

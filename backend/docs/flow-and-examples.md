# Flow & Examples

How the system works end-to-end, with worked examples showing real AI tool call sequences.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  User draws on whiteboard + speaks                                  │
│           │                                                         │
│           ▼                                                         │
│     AI Agent (Claude)                                               │
│     Receives: { visual_delta, audio_transcription, timestamp }      │
│           │                                                         │
│     Decides which graph operations to call                          │
│           │                                                         │
│           ▼  MCP protocol (HTTP to /mcp)                            │
│  ┌─────────────────────────┐                                        │
│  │  FastMCP Server         │                                        │
│  │  localhost:8000         │                                        │
│  │                         │                                        │
│  │  _graph (RAM)  ◀───────── tool calls mutate this                 │
│  │  _session_id            │                                        │
│  └─────────────────────────┘                                        │
│           │                                                         │
│     Frontend sends POST /end-session when user is done              │
│           │                                                         │
│           ▼                                                         │
│     MongoDB Atlas                                                   │
│     system_design.sessions  (one doc — structure)                   │
│     system_design.nodes     (one doc per component — details)       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The Three Phases

### Phase 1 — Live session (in-memory only)

The server starts and creates a single empty `SystemDesignGraph` object and a UUID for this session. Nothing touches MongoDB yet.

As the user draws and speaks, the AI sends MCP tool calls. Each call is a function execution in Python that mutates the in-memory graph. These are instantaneous — no I/O, no network, just Python dict operations.

### Phase 2 — BFS at session end

When the frontend calls `POST /end-session`, the server runs a BFS traversal starting from whichever node was set as the entry point. This walk produces `traversal_order` — the list of node IDs in logical sequence from the user-facing entry inward.

### Phase 3 — MongoDB write

The `SessionStore` makes two writes:
1. One **session document** — the skeleton (edges + traversal order)
2. One **node document per component** — the content (label, type, details, and its `traversal_index` in the BFS walk)

---

## Decision Tree: what tool does the AI call?

```
New component introduced?
│
├── Is it the user-facing entry (browser, CDN, mobile app)?
│     └── createNode() → setEntryPoint()
│
├── Does it belong between two already-connected components?
│     └── getGraphState() to confirm edge exists
│           └── insertNodeBetween()
│
├── Does it connect to something at the edge of the current graph?
│     └── createNode() → addEdge()
│
└── Does it add more information to an existing component?
      └── addDetailsToNode()

User removes or replaces a component?
│
├── Component removed entirely → deleteNode()
└── Connection redirected → removeEdge() → addEdge()

Unsure about current topology before a structural change?
└── getGraphState() — always call this to fact-check first
```

---

## Example 1 — Simple 3-tier web app

**What the user builds:** Browser → API → PostgreSQL

---

**Payload 1**
```json
{
  "visual_delta": "A box labeled 'API' was drawn",
  "audio_transcription": "I'm starting with an API service",
  "current_timestamp": 5
}
```

AI tool calls:
```python
createNode("api", "API", "service")
# → {"status": "created", "node": {"id": "api", "label": "API", "type": "service"}}
```

Graph state:
```
api
```

---

**Payload 2**
```json
{
  "visual_delta": "A box labeled 'PostgreSQL' was drawn with an arrow from 'API'",
  "audio_transcription": "and it writes to a Postgres database",
  "current_timestamp": 18
}
```

AI tool calls:
```python
createNode("db", "PostgreSQL", "database")
addEdge("api", "db", "writes to")
addDetailsToNode("db", {"technology": "PostgreSQL 15"})
```

Graph state:
```
api ──[writes to]──▶ db
```

---

**Payload 3**
```json
{
  "visual_delta": "A box labeled 'Browser' was drawn with an arrow to 'API'",
  "audio_transcription": "users access this from a browser",
  "current_timestamp": 31
}
```

AI tool calls:
```python
createNode("browser", "Client Browser", "client")
addEdge("browser", "api", "HTTP requests")
setEntryPoint("browser")
```

Graph state:
```
browser ──[HTTP requests]──▶ api ──[writes to]──▶ db
Entry point: browser
BFS order:  [browser, api, db]
```

Note: `browser` was created third, but `setEntryPoint` ensures BFS starts there. `db` gets `traversal_index: 2` not `0`.

---

**POST /end-session**

MongoDB writes:
```json
// sessions collection
{
  "_id": "f3a1...",
  "traversal_order": ["browser", "api", "db"],
  "edges": [
    {"from": "browser", "to": "api",  "label": "HTTP requests"},
    {"from": "api",     "to": "db",   "label": "writes to"}
  ]
}

// nodes collection (3 documents)
{"node_id": "browser", "traversal_index": 0, "type": "client",   "details": {}}
{"node_id": "api",     "traversal_index": 1, "type": "service",  "details": {}}
{"node_id": "db",      "traversal_index": 2, "type": "database", "details": {"technology": "PostgreSQL 15"}}
```

---

## Example 2 — Inserting a component between two connected ones

**Scenario:** The user has `browser → api` already in the graph. They then say "actually there's a load balancer in front of the API."

---

**Payload**
```json
{
  "visual_delta": "A 'Load Balancer' box was drawn between 'Browser' and 'API'",
  "audio_transcription": "oh right, there's a load balancer sitting in front of the API",
  "current_timestamp": 44
}
```

AI first fact-checks the current topology:
```python
getGraphState()
# Returns: edges: [{"from": "browser", "to": "api", "label": "HTTP requests"}]
# Confirms: browser → api edge exists
```

AI then inserts:
```python
insertNodeBetween(
    fromId="browser",
    newId="lb",
    newLabel="Load Balancer",
    newType="load_balancer",
    toId="api",
    fromLabel="HTTP requests",
    toLabel="routes to"
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

**Scenario:** The user says "actually, forget the direct connection to Postgres — I want the API to go through Redis first for caching."

---

**Payload**
```json
{
  "visual_delta": "Arrow from 'API' to 'PostgreSQL' erased, new box 'Redis' drawn",
  "audio_transcription": "let me remove the direct DB connection, add a Redis cache in between",
  "current_timestamp": 67
}
```

AI tool calls:
```python
removeEdge("api", "db")
createNode("cache", "Redis Cache", "cache")
addEdge("api", "cache", "reads/writes")
addEdge("cache", "db", "cache miss → writes to")
addDetailsToNode("cache", {"technology": "Redis 7", "strategy": "write-through"})
```

Graph state after:
```
browser → lb → api → cache → db
                       ↑
                  (Redis 7, write-through)
```

---

## Example 4 — Branching design (fan-out)

**Scenario:** An API that writes to two different stores — one relational, one object storage.

---

**Payload**
```json
{
  "visual_delta": "Two arrows drawn from 'API': one to 'PostgreSQL', one to 'S3'",
  "audio_transcription": "the API writes user records to Postgres, and uploads to S3",
  "current_timestamp": 90
}
```

AI tool calls:
```python
createNode("db",  "PostgreSQL", "database")
createNode("s3",  "S3 Bucket",  "storage")
addEdge("api", "db", "writes user records")
addEdge("api", "s3", "uploads files")
addDetailsToNode("db", {"role": "user records"})
addDetailsToNode("s3", {"role": "file uploads", "technology": "AWS S3"})
```

Graph state:
```
browser → lb → api ──[writes user records]──▶ db
                  └──[uploads files]────────▶ s3
```

BFS order from `browser`: `[browser, lb, api, db, s3]`

Both `db` and `s3` are at depth 3 from the entry point. BFS visits them in the order their edges were added — `db` before `s3` here, giving them `traversal_index` 3 and 4 respectively.

---

## Example 5 — Socratic question (AI detects stall)

**Scenario:** The user has been silent for two consecutive payload intervals. The graph has an API and a database but no client or cache.

The AI inspects the graph:
```python
getGraphState()
# Returns: nodes: [api, db], entry_point: null
```

It identifies the missing entry point and speaks:

> "I can see your API and database — where does traffic enter the system? Is there a client, a CDN, or a load balancer at the front?"

This is a Socratic question triggered by the rule in the system prompt: if no changes occur for two or more consecutive intervals, ask about the most critical missing component.

---

## Entry Point Rules

| Situation | What to do |
|-----------|------------|
| User mentions browser, mobile app, CDN first | `createNode` + `setEntryPoint` immediately |
| User draws backend components first, then mentions client | `createNode` client node, `setEntryPoint`, then connect with `addEdge` |
| Entry point node is deleted | Call `setEntryPoint` again on the new logical head |
| Design has no clear single entry (e.g. event-driven) | Set the event source or message broker as entry point |
| Two payloads with no changes | Call `getGraphState`, identify the missing critical component, ask a question |

---

## BFS Traversal and `traversal_index`

`traversal_index` is the position of a node in the BFS walk from the entry point. It captures the user's conceptual order of thinking — from the user-facing layer inward to the data layer.

```
Entry point: browser (index 0)
  → lb       (index 1)
    → api    (index 2)
      → db   (index 3)
      → s3   (index 4)
```

This index is used for scoring: two users who both built a 5-node design can be compared node-by-node at the same depth, independent of what they named things or what order they drew them.

Disconnected nodes (components with no path from the entry point) receive `traversal_index: -1` in MongoDB.

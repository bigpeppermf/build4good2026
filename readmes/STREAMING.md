# Practice session HTTP API

The frontend communicates with the Python backend over plain HTTP. There is no WebSocket. Audio is recorded **locally** in the browser for on-device replay only — it is never sent to the server.

## Endpoint overview

| Method | Path | Caller | Purpose |
|--------|------|--------|---------|
| `POST` | `/new-session` | Frontend | Create a session; returns `session_id` |
| `POST` | `/agent/process-capture` | Frontend | Upload a JPEG still; backend runs the visual-delta pipeline and returns the agent's verbal response |
| `POST` | `/end-session` | Frontend | Save the completed graph to MongoDB |
| `GET`  | `/docs` | Browser | View the full API reference |

> **Dev proxy:** Vite proxies `/api/*` → `http://localhost:8000/*` with path rewriting, so the frontend uses paths like `/api/new-session` in development and they reach the backend without CORS issues.

---

## Session lifecycle

### 1. Start — `POST /new-session`

Called once when the user clicks **Setup**. No request body required.

**Response (200)**
```json
{ "session_id": "f3a1c9d2-4b7e-4f2a-9c3d-1e2b3a4c5d6e" }
```

All subsequent calls include this `session_id`.

---

### 2. Frame capture — `POST /agent/process-capture`

Sent every **15 seconds** while the session is active. The request is `multipart/form-data`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | ID from `POST /new-session` |
| `timestamp_ms` | integer (string-encoded) | Yes | Milliseconds since session start |
| `frame` | file (`image/jpeg`) | Yes | JPEG still captured from the camera `<video>` element |

**Response (200) — frame accepted and processed**
```json
{
  "verbal_response": "Got it — I've added the Load Balancer and connected it to the API service.",
  "visual_delta": "A box labeled 'Load Balancer' was drawn with an arrow to 'API Service'."
}
```

**Response (200) — frame discarded** (person detected, or frame too similar to last accepted)
```json
{ "discarded": true }
```

**Response (404)** — unknown session
```json
{ "error": "Invalid or missing 'session_id'." }
```

> **Implementation note:** `/agent/process-capture` is the endpoint the frontend calls. It is responsible for running the frame through the visual-delta pipeline (person filter → diff filter → OCR → change description) before passing the result to the Gemini agent. See `backend/core/frame_processor.py` and `backend/core/visual_delta_pipeline.py`.

---

### 3. End — `POST /end-session`

Called when the user clicks **Stop session**. Request is `application/json`.

```json
{ "session_id": "f3a1c9d2-..." }
```

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

**Response (400)** — graph is empty
```json
{ "error": "Graph is empty — nothing to save." }
```

---

## Local audio replay

The browser keeps a local `Blob` of the audio-only `MediaRecorder` recording for on-device preview after the session ends. This audio is never uploaded to the backend.

## Environment variable

| Variable | Purpose |
|----------|---------|
| `VITE_API_URL` | Override the API origin in production. In development the Vite proxy handles routing automatically — leave unset. |

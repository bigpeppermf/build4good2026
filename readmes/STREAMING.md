# Practice session WebSocket stream (audio only)

The dashboard streams **audio** over WebSocket. **JPEG stills** are **not** sent on this socket; each capture is posted over HTTP to `POST /agent/process-capture` with the `session_id` from `POST /new-session` (see `backend/docs/api-reference.md`).

## Endpoint

- **Path:** `/api/practice/stream` (dev) → proxied to **`/practice/stream`** on the Python server.
- **URL:** `ws://<host>/api/practice/stream` or `wss://` in production.
- **Dev:** Vite rewrites `/api` to the backend origin and enables **WebSocket upgrade** (`vite.config.ts` → `ws: true`).
- **Override:** set `VITE_PRACTICE_STREAM_WS` to a full WebSocket URL if needed (see `.env.example`).

## Client → server message order

### 1. Session start (text)

Immediately after the socket opens:

```json
{
  "type": "start",
  "session_id": "<uuid from POST /new-session>",
  "audioMime": "audio/webm;codecs=opus",
  "imageMime": "image/jpeg",
  "imageIntervalMs": 15000
}
```

`audioMime` matches what `MediaRecorder` uses for the **audio-only** stream. `imageIntervalMs` is how often the **browser** captures a JPEG for the separate HTTP upload (not sent on this WebSocket).

### 2. Audio chunks (repeated)

For each `MediaRecorder` timeslice (~500 ms):

1. **Text:** `{ "type": "audio_chunk", "seq": <number>, "bytes": <number> }`
2. **Binary:** raw audio fragment.

The current Python server accepts and discards payloads so the connection stays open; you can extend it to buffer or forward audio.

### 3. Session stop (text)

When the user stops, after the audio recorder finishes:

```json
{
  "type": "stop",
  "session_id": "<uuid>",
  "elapsedMs": 12345,
  "audioChunksSent": 42,
  "imageFramesSent": 3,
  "audioMime": "audio/webm;codecs=opus",
  "imageMime": "image/jpeg"
}
```

`imageFramesSent` counts **HTTP** `POST /agent/process-capture` calls that returned success, not WebSocket messages.

### 4. Close

The client then **closes** the WebSocket.

## Visual frames + agent (HTTP)

For each JPEG still, the client sends **multipart** `POST /api/agent/process-capture` with `session_id`, `timestamp_ms`, and `frame` (file). The backend runs the CV / `visual_delta` pipeline for that session, then the agent; the JSON response includes `verbal_response` for the UI (and optional TTS).

## Local replay

The browser keeps a **local** `Blob` of the **audio-only** recording for on-device preview.

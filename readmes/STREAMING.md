# Practice session WebSocket stream

The dashboard sends **full audio** continuously and **JPEG still frames** from the webcam on a fixed interval (default **15 seconds**). Video is **not** streamed as WebM chunks.

## Endpoint

- **Path:** `/api/practice/stream`
- **URL:** `ws://<host>/api/practice/stream` or `wss://` in production.
- **Dev:** Vite proxies `/api` to the API server with **WebSocket upgrade** enabled (`vite.config.ts` → `ws: true`).
- **Override:** set `VITE_PRACTICE_STREAM_WS` to a full WebSocket URL if the stream should not use the page’s host (see `.env.example`).

## Client → server message order

Messages alternate **text (JSON)** and **binary** so the server can parse each payload type.

### 1. Session start (text)

Immediately after the socket opens:

```json
{
  "type": "start",
  "audioMime": "audio/webm;codecs=opus",
  "imageMime": "image/jpeg",
  "imageIntervalMs": 15000
}
```

`audioMime` matches what `MediaRecorder` uses for the **audio-only** stream (browser-dependent). `imageIntervalMs` is the interval between JPEG captures from the live `<video>` preview.

### 2. Audio chunks (repeated)

For each `MediaRecorder` timeslice (client uses ~500 ms):

1. **Text:** `{ "type": "audio_chunk", "seq": <number>, "bytes": <number> }`
2. **Binary:** raw audio fragment (same order as `seq`).

Treat binary fragments as **sequential parts** of one recording; concatenate in order for playback or your pipeline.

### 3. Image frames (repeated)

On each interval tick (first frame after **15 seconds**, then every **15 seconds** while the session is active):

1. **Text:** `{ "type": "image_frame", "seq": <number>, "elapsedMs": <number>, "bytes": <number> }`  
   `elapsedMs` is milliseconds since the WebSocket opened (wall clock on the client).
2. **Binary:** JPEG bytes (`image/jpeg`).

### 4. Session stop (text)

When the user stops, after the audio recorder finishes:

```json
{
  "type": "stop",
  "elapsedMs": 12345,
  "audioChunksSent": 42,
  "imageFramesSent": 3,
  "audioMime": "audio/webm;codecs=opus",
  "imageMime": "image/jpeg"
}
```

### 5. Close

The client then **closes** the WebSocket.

## Server expectations

- Accept WebSocket upgrades on `/api/practice/stream` (or the path your team standardizes—if it changes, update `STREAM_PATH` in `frontend/src/composables/useWhiteboardSession.ts` and this doc).
- Parse JSON lines to know whether the following binary blob is **audio** or **JPEG**, and buffer **audio** chunks in order by `seq`.
- If the socket drops mid-session, the client stops `MediaRecorder` and surfaces an error.

## Local replay

The browser keeps a **local** `Blob` of the **audio-only** recording for on-device preview. JPEG stills are not retained locally for replay; they are only sent to the server.

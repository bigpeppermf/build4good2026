# Practice session WebSocket stream

The dashboard sends **live video + audio** to the backend as **encoded WebM chunks** over a WebSocket (not per-frame JPEG uploads).

## Endpoint

- **Path:** `/api/practice/stream`
- **URL:** `ws://<host>/api/practice/stream` or `wss://` in production.
- **Dev:** Vite proxies `/api` to the API server with **WebSocket upgrade** enabled (`vite.config.ts` → `ws: true`).
- **Override:** set `VITE_PRACTICE_STREAM_WS` to a full WebSocket URL if the stream should not use the page’s host (see `.env.example`).

## Client → server message order

1. **Text (JSON)** immediately after the socket opens:
   ```json
   { "type": "start", "mime": "video/webm;codecs=vp9,opus" }
   ```
   `mime` matches what `MediaRecorder` is using (browser-dependent).

2. **Binary** messages: each `Blob` from `MediaRecorder` **timeslice** events (~500 ms). Treat them as **sequential fragments** of one WebM bitstream; concatenate on the server in order for playback or your pipeline.

3. **Text (JSON)** when the user stops the session (after the recorder flushes):
   ```json
   {
     "type": "stop",
     "elapsedMs": 12345,
     "chunksSent": 42,
     "mime": "video/webm;codecs=vp9,opus"
   }
   ```

4. The client then **closes** the WebSocket.

## Server expectations

- Accept WebSocket upgrades on `/api/practice/stream` (or the path your team standardizes—if it changes, update `STREAM_PATH` in `frontend/src/composables/useWhiteboardSession.ts` and this doc).
- Buffer binary chunks in order; decode or forward to your analysis service as needed.
- If the socket drops mid-session, the client stops `MediaRecorder` and surfaces an error.

## Local replay

The browser also keeps a **local** `Blob` of the full recording for on-device preview only; that is not uploaded via HTTP multipart in the current flow.

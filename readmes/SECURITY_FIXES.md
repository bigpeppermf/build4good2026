# Security Fixes Required

This document describes every security issue identified in the codebase and the exact changes needed to fix each one.

---

### 2. Add CORS Middleware — **Required**

**File:** `backend/server/app.py` — `app` assembly block (~line 524)

Currently the `Starlette` app has no CORS middleware. Any origin can make credentialed requests in a browser.

**What to add:**

Install (already available via starlette):
```
# No extra install needed — CORSMiddleware ships with starlette
```

Add middleware **after** the `Starlette(...)` constructor:

```python
from starlette.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # add production URL here when deploying
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

> For production, replace `"http://localhost:5173"` with your deployed frontend domain. Never use `allow_origins=["*"]` with `allow_credentials=True`.

---

### 3. No Authentication on Any Endpoint

**File:** `backend/server/app.py` — all route handlers

Any caller who knows a `session_id` UUID can read or mutate another user's session. There is zero auth today.

**Minimum viable fix (shared API key):**

Add a middleware that checks a secret header:

```python
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

API_KEY = os.environ["BACKEND_API_KEY"]  # add to .env

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in ("/docs",):          # public paths
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(key, API_KEY):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)
```

Add `BACKEND_API_KEY=<random 32-byte hex>` to `backend/.env`.

The frontend sends the header on every request:
```ts
headers: { "X-API-Key": import.meta.env.VITE_BACKEND_API_KEY }
```

> Longer-term: replace with Clerk JWT verification so sessions are tied to a specific user account.

---

## HIGH

---

### 4. Add File Upload Size Limits

**File:** `backend/server/app.py` — `process_capture` (~line 468) and `end_session` (~line 339)

No size check exists; an attacker can send gigabyte payloads to exhaust memory.

**Add at the top of each upload handler:**

```python
MAX_FRAME_BYTES = 5 * 1024 * 1024   # 5 MB
MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB

# In process_capture:
frame_bytes = await frame_file.read()
if len(frame_bytes) > MAX_FRAME_BYTES:
    return JSONResponse({"error": "frame too large"}, status_code=413)

# In end_session:
audio_bytes = await audio_file.read()
if len(audio_bytes) > MAX_AUDIO_BYTES:
    return JSONResponse({"error": "audio too large"}, status_code=413)
```

Also configure a global body size limit in uvicorn:
```python
uvicorn.run(app, host="0.0.0.0", port=8000, limit_max_requests=1000, h11_max_incomplete_event_size=60_000_000)
```

---

### 5. Add Rate Limiting on Expensive AI Endpoints

**File:** `backend/server/app.py` — `process_capture` and `end_session`

Each call to these endpoints invokes paid Gemini API calls. No throttling = cost attack.

**Install:**
```
uv add slowapi
```

**Add to `app.py`:**
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Decorate the expensive handlers:
@limiter.limit("30/minute")
async def process_capture(request: Request) -> JSONResponse: ...

@limiter.limit("5/minute")
async def end_session(request: Request) -> JSONResponse: ...
```

---

### 6. Fix Prompt Injection in Agent Input

**File:** `backend/agent/agent.py` — line ~282

`visual_delta` is embedded into the LLM prompt via an f-string with `repr()`. This is not sufficient sanitization.

**Change:**
```python
# Before
f'{{"visual_delta": {visual_delta!r}, "current_timestamp": {timestamp_ms}}}\n\n'

# After
import json
json.dumps({"visual_delta": visual_delta, "current_timestamp": timestamp_ms}) + "\n\n"
```

Same pattern applies in `visual_delta_pipeline.py` — use `json.dumps()` / structured prompt objects rather than `.format()` with raw text.

---

### 7. Fix XSS in `/docs` Endpoint

**File:** `backend/server/app.py` — `serve_docs` (~line 50–128)

The HTML page uses `document.getElementById("content").innerHTML = marked.parse(md)` which is an XSS sink.

**Fix:**
```html
<!-- Replace the script block with: -->
<script>
  const md = `{{ escaped_markdown_here }}`;
  marked.setOptions({ headerIds: false, mangle: false });
  const dirty = marked.parse(md);
  // If DOMPurify is available:
  document.getElementById("content").innerHTML = DOMPurify.sanitize(dirty);
</script>
```

Or, since `/docs` is an internal developer page with a static markdown source, the simplest fix is to serve it as a static file rather than rendering server-side.

---

## MEDIUM

---

### 8. Add Security Response Headers

**File:** `backend/server/app.py` — add middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

### 9. Guard `load_dotenv()` to Development Only

**File:** `backend/server/app.py` — line 33

```python
# Before
load_dotenv()

# After
if os.environ.get("ENV") != "production":
    load_dotenv()
```

Set `ENV=production` in your deployment environment. This prevents `.env` from silently overriding real secrets in prod.

---

### 10. Validate MongoDB URI at Startup

**File:** `backend/server/app.py` — line 39

```python
# Before
_store = SessionStore(uri=os.environ["MONGODB_URI"])

# After
_mongo_uri = os.environ.get("MONGODB_URI")
if not _mongo_uri:
    raise RuntimeError("MONGODB_URI environment variable is not set")
_store = SessionStore(uri=_mongo_uri)
```

---

### 11. Add Input Validation to Graph Tool Parameters

**File:** `backend/agent/agent.py` — tool function definitions (~line 110–213)

Use Pydantic to enforce constraints on LLM-generated tool arguments:

```python
from pydantic import BaseModel, Field, field_validator
import re

class NodeParams(BaseModel):
    id: str = Field(..., max_length=64)
    label: str = Field(..., max_length=128)
    type: str = Field(..., max_length=64)

    @field_validator("id")
    @classmethod
    def id_alphanumeric(cls, v: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_\-]+", v):
            raise ValueError("id must be alphanumeric")
        return v
```

---

### 12. Bind to `127.0.0.1` in Development

**File:** `backend/server/app.py` — line 545

```python
# Before
uvicorn.run(app, host="0.0.0.0", port=8000)

# After
host = os.environ.get("HOST", "127.0.0.1")
uvicorn.run(app, host=host, port=8000)
```

Set `HOST=0.0.0.0` explicitly in production (behind a reverse proxy). Default to localhost to reduce accidental exposure during development.

---

## Summary Checklist

| # | Severity | Action | File |
|---|----------|--------|------|
| 1 | CRITICAL | Rotate MongoDB + Google + Clerk credentials | `.env` files |
| 2 | CRITICAL | Add `CORSMiddleware` with explicit origin list | `app.py:524` |
| 3 | CRITICAL | Add `APIKeyMiddleware` (or Clerk JWT verification) | `app.py` |
| 4 | HIGH | Add file upload size limits (5 MB frame, 50 MB audio) | `app.py:468`, `339` |
| 5 | HIGH | Add rate limiting via `slowapi` | `app.py` |
| 6 | HIGH | Replace f-string prompt building with `json.dumps()` | `agent.py:282`, `visual_delta_pipeline.py:91` |
| 7 | HIGH | Sanitize `marked.parse()` output before `innerHTML` | `app.py:123` |
| 8 | MEDIUM | Add `SecurityHeadersMiddleware` | `app.py` |
| 9 | MEDIUM | Guard `load_dotenv()` to non-production | `app.py:33` |
| 10 | MEDIUM | Validate `MONGODB_URI` at startup | `app.py:39` |
| 11 | MEDIUM | Add Pydantic validation to graph tool params | `agent.py:110` |
| 12 | MEDIUM | Default `host` to `127.0.0.1` via env var | `app.py:545` |

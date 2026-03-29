# Post-Session Analysis Pipeline — Design Document

## Overview

When a user ends a whiteboard practice session, Mirage enters a post-session analysis phase. The goal is to (1) validate the in-memory system design graph against the audio recording of the session, (2) correct any discrepancies, (3) persist the validated result to MongoDB, and (4) run a structured analysis that populates the `Analysis`, `Feedback`, and `Score` fields in `ChatView.vue`. A separate chat agent is also seeded with context so the user can ask follow-up questions about their design.

---

## Architecture at a Glance

```
End Session click
       │
       ▼
[1] Finalize audio recording (browser)
       │
       ▼
[2] POST /end-session  (audio blob + session_id)
       │
       ▼
[3] ValidationAgent — compare transcript ↔ graph
       │  (tool calls to mutate graph if needed)
       ▼
[4] Save validated graph → MongoDB
       │
       ▼
[5] AnalysisAgent — score + feedback + summary
       │
       ▼
[6] Store analysis doc → MongoDB
       │
       ▼
[7] Frontend polls / receives SSE → populates ChatView
```

---

## Step-by-Step Design

---

### Step 1 — Finalize Audio Recording (Browser)

**Where:** `frontend/src/composables/useWhiteboardSession.ts`

**What happens:**
- When the user clicks "Start Session", a `MediaRecorder` is started on the audio track of the existing `getUserMedia` stream (video + audio).
- Recorded chunks are accumulated in a `Blob[]` array in memory throughout the session.
- When the user clicks "End Session":
  - `MediaRecorder.stop()` is called; the final `ondataavailable` fires.
  - All chunks are assembled into a single `Blob` with MIME type `audio/webm` (or `audio/ogg` as fallback based on browser support).
  - This blob is **not played back locally** in this flow; it is sent to the backend for validation.

**New composable state:**
```typescript
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])
const audioBlob = ref<Blob | null>(null)
```

**Finalize function:**
```typescript
async function finalizeAudio(): Promise<Blob> {
  return new Promise((resolve) => {
    mediaRecorder.value!.onstop = () => {
      const blob = new Blob(audioChunks.value, { type: 'audio/webm' })
      audioBlob.value = blob
      resolve(blob)
    }
    mediaRecorder.value!.stop()
  })
}
```

**Updated `stopSession()` flow:**
```
stopSession()
  → await finalizeAudio()          // get audio blob
  → await endSessionRequest(blob)  // POST /end-session with audio + session_id
  → display analysis when ready
```

---

### Step 2 — `POST /end-session` — Revised Contract

**Where:** `backend/server/app.py`

**Current contract:** JSON body `{ session_id }`, saves graph to Mongo and returns summary.

**New contract:** `multipart/form-data`
```
session_id   string   (form field)
audio        file     (audio/webm blob from browser)
```

**Backend response:** HTTP 202 Accepted with a job token (the session_id doubles as the job ID).
```json
{ "session_id": "uuid", "status": "processing" }
```

The endpoint kicks off the pipeline asynchronously (using `asyncio.create_task` or a background worker) so the browser does not wait for the full analysis to complete. The frontend then polls `GET /analysis/{session_id}` to get results as they become available.

---

### Step 3 — ValidationAgent

**Where:** `backend/agent/validation_agent.py`
**New file**

**Purpose:** Use the audio transcript of what the user *said* during the session to cross-check the graph that was built from visual frames. Whiteboard OCR can miss labels, misread text, or fail to capture components drawn off-screen. The audio provides a ground-truth signal of the designer's intent.

#### 3a — Transcribe the Audio

Use the **Google Gemini 2.5 Flash** multimodal API to transcribe the audio. Gemini accepts audio blobs inline.

```python
import google.generativeai as genai

async def transcribe_audio(audio_bytes: bytes) -> str:
    model = genai.GenerativeModel("gemini-2.5-flash-lite")
    audio_part = {"mime_type": "audio/webm", "data": audio_bytes}
    response = await model.generate_content_async([
        "Transcribe this audio recording of a system design whiteboard session. "
        "Preserve all technical terms, component names, and architecture descriptions verbatim.",
        audio_part
    ])
    return response.text
```

#### 3b — Build the Validation Prompt

After transcription, the ValidationAgent receives:
- The full audio transcript (plain text)
- The current `graph.bfs_serialize()` output (BFS-ordered text snapshot of all nodes and edges)

**System prompt strategy:**
```
You are a system design auditor. You are given:
1. A TRANSCRIPT of what a developer said while designing on a whiteboard.
2. A GRAPH SNAPSHOT of what was captured visually by the OCR pipeline.

Your job is to identify discrepancies — components or connections mentioned in
the transcript that are absent from the graph, or labels that are clearly
misread (e.g. "Redis" appears as "R3d1s" in the graph).

Use the available tools to correct the graph. Only make changes you are
highly confident about based on explicit mention in the transcript.
Do not add components that are only vaguely implied.

After all corrections, call get_graph_state() and output a single sentence
summarizing what was corrected, or "Graph matches transcript" if no changes
were needed.
```

#### 3c — Available Tools (same as WhiteboardAgent)

The ValidationAgent is bound to the same graph mutation tools:
- `create_node`, `delete_node`, `add_details_to_node`
- `add_edge`, `remove_edge`
- `insert_node_between`
- `get_graph_state`

The agent runs an agentic loop identical to `WhiteboardAgent` — LLM calls tools, receives results, loops until no more tool calls.

#### 3d — Validation Result

```python
@dataclass
class ValidationResult:
    transcript: str              # raw transcript text
    corrections_made: int        # number of graph mutations performed
    validation_summary: str      # agent's one-sentence summary
    graph_confidence: float      # 0.0–1.0: 1.0 = perfect match, lower = many corrections
```

`graph_confidence` is derived heuristically:
```
1.0 - min(1.0, corrections_made / max(1, len(graph.nodes)))
```

---

### Step 4 — Save Validated Graph to MongoDB

**Where:** `backend/core/session_store.py`

Once the ValidationAgent finishes, save everything in one atomic operation. Extend the existing `save_session()` function:

**`sessions` collection document (extended):**
```json
{
  "_id": "session_id",
  "created_at": "ISO datetime",
  "traversal_order": ["client", "lb", "api", "db"],
  "edges": [{"from": "client", "to": "lb", "label": ""}],
  "audio_transcript": "The user said...",
  "validation_corrections": 2,
  "validation_summary": "Added missing Redis cache node mentioned by user.",
  "graph_confidence": 0.85
}
```

**`nodes` collection documents** — unchanged format, but now reflect the post-validation state of the graph.

---

### Step 5 — AnalysisAgent

**Where:** `backend/agent/analysis_agent.py`
**New file**

**Purpose:** Produce structured, rubric-based analysis of the validated system design. This is a single-shot LLM call (no tool loop required) that outputs the three fields shown in `ChatView.vue`.

#### Input to AnalysisAgent

The agent receives a structured prompt containing:
1. **BFS graph serialization** — full text snapshot of the validated graph
2. **Audio transcript** — for understanding the designer's reasoning
3. **Session metadata** — total session duration, number of frames processed, number of agent responses

#### Output Schema

The agent is asked to produce JSON conforming to:

```typescript
interface AnalysisOutput {
  // "Analysis" field in ChatView — structural assessment
  analysis: {
    architecture_pattern: string          // e.g. "3-tier web architecture"
    component_count: number
    identified_components: string[]       // ["Load Balancer", "API Server", "PostgreSQL DB"]
    connection_density: string            // "sparse" | "moderate" | "dense"
    entry_point: string | null
    disconnected_components: string[]     // nodes with no edges
    bottlenecks: string[]                 // single points of failure or overloaded nodes
    missing_standard_components: string[] // e.g. ["CDN", "Cache layer", "Message queue"]
    summary: string                       // 2–3 sentence plain-English overview
  }

  // "Feedback" field in ChatView — actionable improvement suggestions
  feedback: {
    strengths: string[]       // what the design got right (1–3 items)
    improvements: string[]    // specific, actionable suggestions (2–5 items)
    critical_gaps: string[]   // must-fix issues for correctness (0–3 items)
    narrative: string         // 2–3 sentence coaching paragraph
  }

  // "Score" field in ChatView — numeric score with breakdown
  score: {
    total: number             // 0–100
    breakdown: {
      completeness: number    // 0–25: are all key layers present?
      scalability: number     // 0–25: horizontal scaling, load balancing, caching
      reliability: number     // 0–25: redundancy, no single point of failure
      clarity: number         // 0–25: clean graph, unambiguous connections
    }
    grade: string             // "A" | "B" | "C" | "D" | "F"
  }
}
```

#### Scoring Rubric

| Dimension | 0–25 pts | What earns points |
|-----------|----------|-------------------|
| **Completeness** | 0–25 | Client, network entry (CDN/LB), app layer, data layer each worth ~6 pts. +1 per bonus component (queue, cache, monitoring). |
| **Scalability** | 0–25 | Load balancer (+8), horizontal app tier (+7), caching layer (+5), async queue (+5). |
| **Reliability** | 0–25 | Redundant nodes (+10), no isolated single-node critical path (+8), explicit failure notes in annotations (+7). |
| **Clarity** | 0–25 | All nodes labeled (+5), no disconnected components (+10), entry point set (+5), edges labeled (+5). |

Grade thresholds: A ≥ 90, B ≥ 75, C ≥ 60, D ≥ 45, F < 45.

#### AnalysisAgent System Prompt (abbreviated)

```
You are an expert system design interviewer evaluating a candidate's whiteboard design.
You will receive a graph snapshot of their architecture and the audio transcript of
what they said while drawing.

Produce a JSON response that strictly conforms to the AnalysisOutput schema.

Be specific — name actual components from their graph in feedback.
Be constructive — frame gaps as opportunities, not failures.
Score honestly using the provided rubric.
```

---

### Step 6 — Store Analysis in MongoDB

**Where:** `backend/core/session_store.py`

New function `save_analysis(session_id, analysis_output)`:

**New collection: `analysis`**
```json
{
  "_id": "session_id",
  "created_at": "ISO datetime",
  "analysis": { ... },
  "feedback": { ... },
  "score": {
    "total": 78,
    "breakdown": { "completeness": 20, "scalability": 18, "reliability": 22, "clarity": 18 },
    "grade": "B"
  },
  "chat_seed_context": "<condensed graph + analysis for chat agent>"
}
```

The `chat_seed_context` field is a condensed text summary injected into the chat agent's system prompt so the user can ask questions about their design without the chat agent needing to re-read the raw graph.

---

### Step 7 — Frontend: Polling & Display

**Where:** `frontend/src/views/ChatView.vue` + new composable `useSessionAnalysis.ts`

#### 7a — Polling Endpoint

New backend endpoint: `GET /analysis/{session_id}`

Response when processing:
```json
{ "status": "processing", "stage": "validation" }
```

Response when done:
```json
{
  "status": "complete",
  "analysis": { ... },
  "feedback": { ... },
  "score": { "total": 78, "grade": "B", "breakdown": { ... } }
}
```

Frontend polls every 2 seconds until `status === "complete"`, then stops.

#### 7b — ChatView Updates

**`Analysis` block** — replaces `—` placeholder:
```
3-tier web architecture · 7 components · moderate connectivity
Entry point: Browser → Load Balancer
Missing: Cache layer, CDN
[2–3 sentence summary from analysis.summary]
```

**`Feedback` block** — replaces `—` placeholder:
```
Strengths:
• Load balancer correctly placed before API tier
• Database properly isolated from client

Improvements:
• Add a Redis cache between API Server and PostgreSQL to reduce read latency
• Consider a CDN for static asset delivery

[narrative paragraph]
```

**`Score` block** — replaces `—` placeholder:
```
78 / 100  ·  B

Completeness  ████████████████████░░░░░  20/25
Scalability   ██████████████████░░░░░░░  18/25
Reliability   ██████████████████████░░░  22/25
Clarity       ██████████████████░░░░░░░  18/25
```

#### 7c — Chat Seeding

When `status === "complete"`, the first message in the chat is pre-populated as an assistant message (not streamed in — displayed immediately):

```
Your session has been analyzed. I've reviewed your system design and generated
feedback above. Feel free to ask me anything about your architecture — for example,
why a certain component was flagged, how to fix a specific gap, or how your design
would handle a specific failure scenario.
```

The chat backend route `POST /chat` (new) accepts:
```json
{ "session_id": "uuid", "message": "Why did I lose points on scalability?" }
```

And passes the message to a `ChatAgent` initialized with `chat_seed_context` from the `analysis` MongoDB document.

---

## New Files Summary

| File | Purpose |
|------|---------|
| `backend/agent/validation_agent.py` | Audio transcript → graph validation + correction |
| `backend/agent/analysis_agent.py` | Validated graph → Analysis / Feedback / Score JSON |
| `backend/agent/chat_agent.py` | Session-aware Q&A chat using stored analysis context |
| `frontend/src/composables/useSessionAnalysis.ts` | Polling, state management for analysis display |

## Modified Files Summary

| File | Change |
|------|--------|
| `backend/server/app.py` | `POST /end-session` accepts audio blob; new `GET /analysis/{id}`; new `POST /chat` |
| `backend/core/session_store.py` | Extended session doc; new `save_analysis()` function; new `analysis` collection |
| `frontend/src/composables/useWhiteboardSession.ts` | Wire up `MediaRecorder`; send audio on end session |
| `frontend/src/views/ChatView.vue` | Consume `useSessionAnalysis`; render Analysis / Feedback / Score; seed chat |

---

## Data Flow Sequence Diagram

```
Browser                   Backend                    MongoDB
  │                          │                          │
  │── click End Session ─────│                          │
  │                          │                          │
  │   finalizeAudio()        │                          │
  │   (MediaRecorder.stop)   │                          │
  │                          │                          │
  │── POST /end-session ────▶│                          │
  │   (audio blob +          │                          │
  │    session_id)           │                          │
  │                          │                          │
  │◀─ 202 Accepted ──────────│                          │
  │   { status: processing } │                          │
  │                          │                          │
  │   (background task)      │── transcribe_audio() ──▶│
  │                          │   (Gemini audio API)     │
  │                          │                          │
  │                          │◀─ transcript ────────────│
  │                          │                          │
  │                          │   ValidationAgent        │
  │                          │   (transcript ↔ graph)   │
  │                          │   (tool calls if needed) │
  │                          │                          │
  │                          │── save_session() ───────▶│ sessions + nodes
  │                          │                          │
  │                          │   AnalysisAgent          │
  │                          │   (graph + transcript)   │
  │                          │                          │
  │                          │── save_analysis() ──────▶│ analysis
  │                          │                          │
  │── GET /analysis/{id} ───▶│                          │
  │                          │◀─ analysis doc ──────────│
  │◀─ { status: complete,    │                          │
  │    analysis, feedback,   │                          │
  │    score } ──────────────│                          │
  │                          │                          │
  │   Render ChatView        │                          │
  │   (Analysis/Feedback/    │                          │
  │    Score populated)      │                          │
```

---

## Open Questions / Decisions Needed

1. **Audio privacy:** The current STREAMING.md states audio is never sent to the server. This design reverses that. Confirm this change is acceptable, or alternatively explore client-side transcription via the Web Speech API (less accurate, no cross-browser guarantee).

2. **Gemini audio support:** Verify that the `gemini-2.5-flash-lite` model in use supports inline audio blobs, or whether `gemini-2.5-flash` (full) is required for audio transcription.

3. **Async execution model:** The current Starlette app is single-process. Use `asyncio.create_task()` for background processing or add a task queue (e.g., `arq` with Redis) if sessions are expected to process concurrently.

4. **Chat route:** The `POST /chat` route needs session authentication or at minimum a session token to prevent unauthorized access to another user's session context.

5. **Session navigation:** Currently `ChatView.vue` is not linked to a specific session ID. A routing parameter (`/chat/:sessionId`) or a shared store (Pinia) will be needed to pass the session ID from DashboardView to ChatView after a session ends.

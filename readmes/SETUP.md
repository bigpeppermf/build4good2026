# Setup and development

Two independent servers:

| Server | Stack | Port |
|--------|-------|------|
| **Backend** | Python 3.12 + FastMCP + Uvicorn | 8000 |
| **Frontend** | Vite + Vue 3 + TypeScript | 5173 |

---

## Prerequisites

- **Python 3.12+** with [uv](https://docs.astral.sh/uv/) (`brew install uv` or `pip install uv`)
- **Node.js 18+** with npm

---

## First-time setup

```bash
# 1. Copy env template and fill in values
cp .env.example .env
#    Required keys:
#      MONGODB_URI     — MongoDB Atlas connection string
#      GOOGLE_API_KEY  — Google AI Studio key (aistudio.google.com/apikey)

# 2. Install Python dependencies (creates backend/.venv automatically)
cd backend
uv sync
cd ..

# 3. Install frontend dependencies
cd frontend
npm install
cd ..
```

---

## Running the servers

Each server must be started in its own terminal.

### Backend (Python MCP server + Gemini agent)

```bash
cd backend
uv run main.py
```

Expected output:
```
Session ID   : <uuid>
MCP          : http://localhost:8000/mcp
Process frame: POST http://localhost:8000/agent/process-frame
End session  : POST http://localhost:8000/end-session
```

### Frontend (Vue dev server)

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

> The Vite dev server proxies `/api/*` → `http://localhost:8000/*` so the
> frontend talks to the Python backend without CORS issues.

---

## Running tests

### Backend

Tests live in `backend/tests/` and use **pytest**.

```bash
cd backend

# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a single file
uv run pytest tests/test_graph.py

# Run with coverage report
uv run pytest --cov=core --cov=agent --cov-report=term-missing
```

> **Note:** No API key is needed to run the test suite. The Gemini LLM is
> replaced with a `MagicMock` in all agent tests, so tests run fully offline.

### Frontend

```bash
cd frontend

# Type-check only (no test runner configured yet)
npm run type-check

# Lint
npm run lint
```

---

## Layout

```
build4good2026/
├── backend/              # Python backend
│   ├── agent/            # LangChain + Gemini vision agent
│   ├── core/             # In-memory graph + MongoDB session store
│   ├── graph_mcp/        # FastMCP server + HTTP endpoints
│   ├── docs/             # API reference + flow examples
│   ├── tests/            # pytest test suite
│   ├── main.py           # Entry point  →  uv run main.py
│   └── pyproject.toml    # Python dependencies
│
├── frontend/             # Vue 3 frontend
│   ├── src/
│   │   ├── composables/  # useWhiteboardSession (camera + frame capture)
│   │   ├── views/        # DashboardView, HomeView
│   │   └── types/        # Shared TypeScript types
│   ├── vite.config.ts    # Proxy: /api → localhost:8000
│   └── package.json
│
├── readmes/              # Project-level documentation
│   ├── SETUP.md          # This file
│   └── BACKEND_DOCS.md   # System overview and component descriptions
│
└── .env.example          # Template for required environment variables
```

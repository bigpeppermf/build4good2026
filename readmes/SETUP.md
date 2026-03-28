# Setup and development

Monorepo skeleton: **frontend** (Vite + Vue 3 + TypeScript) and **backend** (Express + TypeScript).

## Setup

```bash
cp .env.example .env
npm install
```

## Dev

```bash
npm run dev
```

- Web: http://localhost:5173 (proxies `/api` → backend)
- API: http://localhost:3001

Or run one side: `npm run dev:web` / `npm run dev:api`

## Build

```bash
npm run build
```

Run API after build: `npm run start -w backend`

## Layout

- `frontend/` — UI
- `backend/` — HTTP API (`/api/health` wired as a smoke check)

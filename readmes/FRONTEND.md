# Frontend

**Mirage** — whiteboard interview practice (frontend notes).

**Stack:** Vite + Vue 3 + TypeScript

## Current phase

Dashboard: **`POST /new-session`** (via `apiUrl` + Vite `/api` proxy) stores **`session_id`**; **JPEG** stills every **15s** go to **`POST /agent/process-capture`**; **`POST /end-session`** runs on stop. **`verbal_response`** text is listed in the dashboard and optionally spoken (TTS). **Audio** uses WebSocket `/api/practice/stream`. See [STREAMING.md](STREAMING.md).

## Layout decisions

### Sidebar navigation (`AppNav.vue`)
- Vertical sidebar fixed to the left edge, full viewport height
- User placeholder at the top (avatar circle + "User" label) — will be wired to real user data later
- Nav links stacked vertically below the user section (Home, Dashboard)
- Main content area offset by `--sidebar-width` (13rem default, 10rem on mobile)

### Dashboard (`DashboardView.vue`)
- "Practice session" heading pinned top-left, no subtitle/caption
- Section boxes (whiteboard capture, previous sessions) fill the full width proportionally
- Removed the "Dashboard" label and descriptive copy — keeping the UI clean and minimal

### Camera fullscreen overlay
- Clicking "Setup" opens the camera in a fullscreen overlay (`Teleport` to `<body>`, `position: fixed; inset: 0`)
- X button (top-right) closes the overlay and stops the session
- "Stop session" button at the bottom also closes the overlay
- Stats, timer chip, recording badge, and frame guide all render inside the overlay
- Dashboard remains untouched underneath; overlay sits above everything (z-index 100)

### Home page (`HomeView.vue`)
- Removed "Open dashboard" button — only the Start and Begin capture links remain

### Login page (`LoginView.vue`)
- Route: `/login`
- Placeholder for Clerk auth — email/password fields and sign-in button (all disabled)
- Same card style as the rest of the site (elevated card, rose border, matching fonts)
- Will be replaced with actual Clerk components when integrated

### Chat page (`ChatView.vue`)
- Route: `/chat`
- Split 50/50 layout: chat on the left, AI output on the right (stacks vertically on mobile)
- Left panel: message list with user/assistant bubbles, text input bar, send button
- Right panel: placeholder slots for Analysis, Feedback, and Score — will display AI model output once backend is connected
- "Open chat" button in the Previous sessions section navigates here

### Typography
- **Jura** for `--font-mono` and `--font-serif` (nav, labels, stats, hero accent line, etc.)
- **Syne** (display headings), **Source Sans 3** (body / UI sans)

## Open design questions

- Whiteboard component / canvas approach
- How AI assistance surfaces in the UI
- User flow for an interview session

## Notes

- This is a hackathon project (3-person team)
- Frontend is owned by Roni
- Details on AI integration, backend interaction, and feature scope TBD

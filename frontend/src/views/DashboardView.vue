<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { useMirageAuth } from "../composables/useMirageAuth";
import {
  useWhiteboardSession,
  type FrameCropNorm,
} from "../composables/useWhiteboardSession";
import {
  getRecentSessions,
  persistWhiteboardSnapshot,
} from "../utils/sessionOutputStorage";
const {
  videoRef,
  activeStream,
  isSettingUp,
  isBeginningSession,
  isSessionActive,
  errorMessage,
  uploadMessage,
  uploadOk,
  uploadState,
  frameCropNorm,
  lastCompletedSessionId,
  verbalResponses,
  lastCaptureError,
  lastCaptureProcessStatus,
  lastCaptureActivity,
  captureInFlight,
  sessionId,
  imageFramesSentCount,
  discardedFramesCount,
  processedFramesCount,
  sessionTimeLabel,
  openCameraSetup,
  beginSession,
  stopSession,
} = useWhiteboardSession();

const { userId } = useMirageAuth();
const router = useRouter();
const cameraOpen = ref(false);
const currentUserId = computed(() => userId.value ?? null);
const recentSessionsList = ref<{ sessionId: string; savedAt: string }[]>([]);

watch(
  currentUserId,
  (nextUserId) => {
    recentSessionsList.value = nextUserId ? getRecentSessions(nextUserId) : [];
  },
  { immediate: true },
);

function formatSavedAt(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function shortSessionId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

const previewRef = ref<HTMLElement | null>(null);

const MIN_FR = 0.08;

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n));
}

function clampFrame(r: FrameCropNorm): FrameCropNorm {
  let { left, top, width, height } = r;
  width = clamp(width, MIN_FR, 1);
  height = clamp(height, MIN_FR, 1);
  left = clamp(left, 0, 1 - width);
  top = clamp(top, 0, 1 - height);
  return { left, top, width, height };
}

const frameStyle = computed(() => ({
  left: `${frameCropNorm.value.left * 100}%`,
  top: `${frameCropNorm.value.top * 100}%`,
  width: `${frameCropNorm.value.width * 100}%`,
  height: `${frameCropNorm.value.height * 100}%`,
}));

const captureFrameAria = computed(() => {
  if (isSessionActive.value) {
    switch (lastCaptureProcessStatus.value) {
      case "success":
        return "Crop frame is locked while live. Last still was processed successfully.";
      case "error":
        return "Crop frame is locked while live. Last still failed to process.";
      default:
        return "Crop frame is locked while the session is live.";
    }
  }
  switch (lastCaptureProcessStatus.value) {
    case "success":
      return "Crop frame. Last still was processed successfully.";
    case "error":
      return "Crop frame. Last still failed to process.";
    default:
      return "Crop frame. Drag to move or use handles to resize.";
  }
});

type DragKind = "move" | "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

const dragState = ref<{
  kind: DragKind;
  frame0: FrameCropNorm;
  nx0: number;
  ny0: number;
} | null>(null);

function normFromEvent(e: PointerEvent, el: HTMLElement) {
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) {
    return { nx: 0, ny: 0 };
  }
  return {
    nx: (e.clientX - r.left) / r.width,
    ny: (e.clientY - r.top) / r.height,
  };
}

function startDrag(kind: DragKind, e: PointerEvent) {
  if (isSessionActive.value) {
    return;
  }
  if (!previewRef.value) {
    return;
  }
  e.preventDefault();
  e.stopPropagation();
  const { nx, ny } = normFromEvent(e, previewRef.value);
  dragState.value = {
    kind,
    frame0: { ...frameCropNorm.value },
    nx0: nx,
    ny0: ny,
  };
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  window.addEventListener("pointermove", onDragMove);
  window.addEventListener("pointerup", onDragEnd);
  window.addEventListener("pointercancel", onDragEnd);
}

function onDragMove(e: PointerEvent) {
  if (isSessionActive.value) {
    onDragEnd();
    return;
  }
  if (!dragState.value || !previewRef.value) {
    return;
  }
  const { nx, ny } = normFromEvent(e, previewRef.value);
  const { kind, frame0: f0 } = dragState.value;
  const right = f0.left + f0.width;
  const bottom = f0.top + f0.height;
  let r: FrameCropNorm = { ...f0 };

  switch (kind) {
    case "move": {
      const d = dragState.value;
      r.left = f0.left + (nx - d.nx0);
      r.top = f0.top + (ny - d.ny0);
      break;
    }
    case "se":
      r.width = nx - f0.left;
      r.height = ny - f0.top;
      break;
    case "nw":
      r.left = nx;
      r.top = ny;
      r.width = right - nx;
      r.height = bottom - ny;
      break;
    case "ne":
      r.top = ny;
      r.width = nx - f0.left;
      r.height = bottom - ny;
      break;
    case "sw":
      r.left = nx;
      r.width = right - nx;
      r.height = ny - f0.top;
      break;
    case "n":
      r.top = ny;
      r.height = bottom - ny;
      break;
    case "s":
      r.height = ny - f0.top;
      break;
    case "w":
      r.left = nx;
      r.width = right - nx;
      break;
    case "e":
      r.width = nx - f0.left;
      break;
    default:
      return;
  }
  frameCropNorm.value = clampFrame(r);
}

function onDragEnd() {
  dragState.value = null;
  window.removeEventListener("pointermove", onDragMove);
  window.removeEventListener("pointerup", onDragEnd);
  window.removeEventListener("pointercancel", onDragEnd);
}

function handleNewSession() {
  cameraOpen.value = true;
  void openCameraSetup();
}

function handleStartSession() {
  void beginSession();
}

async function handleClose() {
  const sid = sessionId.value;
  const activeUserId = currentUserId.value;
  cameraOpen.value = false;
  await stopSession();
  if (sid && activeUserId) {
    persistWhiteboardSnapshot({
      userId: activeUserId,
      sessionId: sid,
      savedAt: new Date().toISOString(),
      verbalResponses: verbalResponses.value.map((v) => ({
        timestampMs: v.timestampMs,
        verbalResponse: v.verbalResponse,
        visualDelta: v.visualDelta,
      })),
      imageFramesSentCount: imageFramesSentCount.value,
      discardedFramesCount: discardedFramesCount.value,
      processedFramesCount: processedFramesCount.value,
      uploadOk: uploadOk.value,
      uploadMessage: uploadMessage.value,
    });
  }
  recentSessionsList.value = activeUserId ? getRecentSessions(activeUserId) : [];
  const targetSessionId = lastCompletedSessionId.value ?? sid;
  if (!targetSessionId) {
    return;
  }
  void router.push({
    name: "chat",
    params: { sessionId: targetSessionId },
    query: { session: targetSessionId },
  });
}
</script>

<template>
  <div class="dashboard">
    <div class="dashboard-inner">
      <h1 class="dashboard-title">
        Practice session
      </h1>

      <div class="dashboard-main">
      <section
        class="capture"
        aria-labelledby="capture-title"
      >
        <h2
          id="capture-title"
          class="capture-title"
        >
          Whiteboard practice session
        </h2>
        <p class="capture-desc">
          Open your camera, frame the board, then start to stream captures to the agent.
          Each still is analyzed on a timer; responses appear below when you return.
        </p>

        <div class="capture-actions">
          <button
            type="button"
            class="btn-new-session"
            :disabled="isSettingUp || isSessionActive || cameraOpen"
            @click="handleNewSession"
          >
            {{ isSettingUp ? "Opening camera…" : "New session" }}
          </button>
        </div>

        <p
          v-if="errorMessage && !cameraOpen"
          class="capture-error"
          role="alert"
        >
          {{ errorMessage }}
        </p>

        <p
          v-if="uploadState === 'uploading'"
          class="upload-status"
        >
          Ending session…
        </p>
        <p
          v-else-if="uploadMessage"
          class="upload-status"
          :class="{ ok: uploadOk === true }"
        >
          {{ uploadMessage }}
        </p>

        <div
          v-if="verbalResponses.length > 0"
          class="verbal-panel"
          aria-live="polite"
        >
          <h3 class="verbal-panel-title">
            Agent responses
          </h3>
          <ol class="verbal-list">
            <li
              v-for="(item, idx) in verbalResponses"
              :key="idx"
              class="verbal-item"
            >
              <span class="verbal-time">{{ (item.timestampMs / 1000).toFixed(1) }}s</span>
              <p class="verbal-text">
                {{ item.verbalResponse }}
              </p>
            </li>
          </ol>
        </div>

    <!-- Fullscreen camera overlay -->
    <Teleport to="body">
      <div
        v-if="cameraOpen"
        class="camera-overlay"
      >
        <button
          type="button"
          class="camera-close"
          aria-label="Close camera"
          @click="handleClose"
        >
          &times;
        </button>

        <p
          v-if="errorMessage"
          class="camera-error"
          role="alert"
        >
          {{ errorMessage }}
        </p>

        <p
          v-if="lastCaptureError && isSessionActive"
          class="camera-capture-error"
          role="status"
        >
          {{ lastCaptureError }}
        </p>

        <p
          v-if="isSessionActive && lastCaptureActivity"
          class="camera-session-status"
          role="status"
        >
          {{ lastCaptureActivity }}
        </p>

        <div
          v-show="activeStream"
          ref="previewRef"
          class="camera-preview"
        >
          <video
            ref="videoRef"
            class="camera-video"
            playsinline
            muted
            autoplay
          />
          <div
            class="frame-guide"
            aria-hidden="true"
          >
            <div
              class="frame-crop-box"
              :class="{
                'frame-crop-box--locked': isSessionActive,
                'frame-crop-box--process-ok': lastCaptureProcessStatus === 'success',
                'frame-crop-box--process-err': lastCaptureProcessStatus === 'error',
              }"
              :style="frameStyle"
              :aria-label="captureFrameAria"
            >
              <span
                class="frame-corner-decor frame-corner-decor--tl"
                aria-hidden="true"
              />
              <span
                class="frame-corner-decor frame-corner-decor--tr"
                aria-hidden="true"
              />
              <span
                class="frame-corner-decor frame-corner-decor--bl"
                aria-hidden="true"
              />
              <span
                class="frame-corner-decor frame-corner-decor--br"
                aria-hidden="true"
              />
              <div
                class="frame-move"
                @pointerdown="startDrag('move', $event)"
              />
              <button
                type="button"
                class="frame-handle frame-handle--nw"
                aria-label="Resize frame northwest"
                @pointerdown="startDrag('nw', $event)"
              />
              <button
                type="button"
                class="frame-handle frame-handle--n"
                aria-label="Resize frame north"
                @pointerdown="startDrag('n', $event)"
              />
              <button
                type="button"
                class="frame-handle frame-handle--ne"
                aria-label="Resize frame northeast"
                @pointerdown="startDrag('ne', $event)"
              />
              <button
                type="button"
                class="frame-handle frame-handle--e"
                aria-label="Resize frame east"
                @pointerdown="startDrag('e', $event)"
              />
              <button
                type="button"
                class="frame-handle frame-handle--se"
                aria-label="Resize frame southeast"
                @pointerdown="startDrag('se', $event)"
              />
              <button
                type="button"
                class="frame-handle frame-handle--s"
                aria-label="Resize frame south"
                @pointerdown="startDrag('s', $event)"
              />
              <button
                type="button"
                class="frame-handle frame-handle--sw"
                aria-label="Resize frame southwest"
                @pointerdown="startDrag('sw', $event)"
              />
              <button
                type="button"
                class="frame-handle frame-handle--w"
                aria-label="Resize frame west"
                @pointerdown="startDrag('w', $event)"
              />
            </div>
          </div>
          <div
            v-if="isSessionActive"
            class="live-timer-cluster"
            role="status"
            :aria-label="`Live, elapsed ${sessionTimeLabel}`"
          >
            <p class="recording-badge">
              Live
            </p>
            <div class="timer-chip">
              {{ sessionTimeLabel }}
            </div>
            <div
              v-if="captureInFlight"
              class="camera-working-pill"
              aria-live="polite"
            >
              <span
                class="camera-working-dot"
                aria-hidden="true"
              />
              Processing still…
            </div>
          </div>
        </div>

        <div class="camera-bottom">
          <button
            v-if="!isSessionActive"
            type="button"
            class="btn-start"
            :disabled="!activeStream || isBeginningSession || isSettingUp"
            @click="handleStartSession"
          >
            {{ isBeginningSession ? "Starting…" : "Start session" }}
          </button>
          <button
            v-else
            type="button"
            class="btn-stop"
            @click="handleClose"
          >
            Stop session
          </button>
        </div>
      </div>
    </Teleport>
      </section>

      <section
        class="recent-sessions"
        aria-labelledby="recent-sessions-title"
      >
        <h2
          id="recent-sessions-title"
          class="recent-sessions-title"
        >
          Saved in this browser
        </h2>
        <p
          v-if="recentSessionsList.length === 0"
          class="recent-sessions-empty"
        >
          When you stop a live session, coach output and stats are stored here. Open Chat to review the snapshot.
        </p>
        <ul
          v-else
          class="recent-sessions-list"
        >
          <li
            v-for="row in recentSessionsList"
            :key="row.sessionId"
            class="recent-sessions-item"
          >
            <RouterLink
              class="recent-sessions-link"
              :to="{
                name: 'chat',
                params: { sessionId: row.sessionId },
                query: { session: row.sessionId },
              }"
            >
              <span class="recent-sessions-id">{{ shortSessionId(row.sessionId) }}</span>
              <span class="recent-sessions-time">{{ formatSavedAt(row.savedAt) }}</span>
            </RouterLink>
          </li>
        </ul>
        <RouterLink
          :to="{ name: 'chat' }"
          class="btn-recent-chat"
        >
          Open Chat
        </RouterLink>
      </section>
      </div>

    </div>
  </div>
</template>

<style scoped>
.dashboard {
  width: 100%;
  max-width: 100%;
  padding: clamp(1.5rem, 4vw, 2.75rem) 0;
}

.dashboard-inner {
  width: 100%;
  max-width: 100%;
  padding: 0 clamp(1rem, 3vw, 2rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: clamp(1rem, 2.5vw, 1.35rem);
}

.dashboard-title {
  width: 100%;
  max-width: min(72rem, 100%);
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.65rem, 4vw + 0.5rem, 2.35rem);
  font-weight: 700;
  color: var(--pop);
  letter-spacing: -0.03em;
  line-height: 1.1;
  text-align: left;
}

.dashboard-main {
  width: 100%;
  max-width: min(72rem, 100%);
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr;
  gap: clamp(1.25rem, 3.5vw, 1.75rem);
  align-items: start;
}

@media (min-width: 960px) {
  .dashboard-main {
    grid-template-columns: 1fr 1fr;
  }
}

.capture {
  margin: 0;
  min-width: 0;
  padding: clamp(1.25rem, 3.5vw, 1.75rem) clamp(1.25rem, 3.5vw, 1.75rem);
  border: 1px dashed rgb(224 112 86 / 0.55);
  border-radius: 4px;
  background-color: rgb(224 112 86 / 0.07);
  box-shadow:
    0 1px 0 rgb(224 112 86 / 0.12) inset,
    0 24px 48px -32px rgb(0 0 0 / 0.5);
  text-align: center;
}

.capture-title {
  margin: 0 0 0.65rem;
  font-size: clamp(1rem, 0.95rem + 0.3vw, 1.1rem);
  font-weight: 700;
  color: var(--pop);
}

.capture-desc {
  margin: 0 auto 1.15rem;
  max-width: min(36rem, 100%);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  line-height: 1.55;
  color: var(--ink-muted);
  text-wrap: pretty;
}

.recent-sessions {
  margin: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: clamp(1.25rem, 3.5vw, 1.75rem) clamp(1.25rem, 3.5vw, 1.75rem);
  border: 1px dashed rgb(224 112 86 / 0.55);
  border-radius: 4px;
  background-color: rgb(224 112 86 / 0.06);
  box-shadow:
    0 1px 0 rgb(224 112 86 / 0.1) inset;
  text-align: center;
}

.recent-sessions-title {
  margin: 0 0 0.65rem;
  font-family: var(--font-display);
  font-size: clamp(1rem, 0.95rem + 0.25vw, 1.125rem);
  font-weight: 600;
  color: var(--pop);
  letter-spacing: -0.02em;
}

.recent-sessions-empty {
  margin: 0 auto 1rem;
  max-width: 100%;
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  line-height: 1.55;
  color: var(--ink-muted);
  text-wrap: pretty;
}

.recent-sessions-list {
  list-style: none;
  margin: 0 0 1rem;
  padding: 0;
  width: 100%;
  max-width: 22rem;
  text-align: left;
}

.recent-sessions-item {
  margin: 0;
  padding: 0;
  border-bottom: 1px solid rgb(224 112 86 / 0.2);
}

.recent-sessions-item:last-child {
  border-bottom: none;
}

.recent-sessions-link {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.55rem 0.15rem;
  text-decoration: none;
  color: inherit;
  transition: color 0.15s ease;
}

.recent-sessions-link:hover {
  color: var(--pop);
}

.recent-sessions-id {
  font-family: var(--font-mono);
  font-size: clamp(0.75rem, 0.72rem + 0.1vw, 0.8125rem);
  font-weight: 600;
  color: var(--ink);
}

.recent-sessions-time {
  font-family: var(--font-mono);
  font-size: clamp(0.625rem, 0.6rem + 0.1vw, 0.6875rem);
  font-weight: var(--font-mono-weight);
  color: var(--ink-muted);
}

.btn-recent-chat {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  padding: 0.65rem 1.15rem;
  width: min(100%, 20rem);
  font-family: var(--font-display);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  text-decoration: none;
  color: var(--ink);
  background: var(--surface-faint);
  border: 1px dashed rgb(224 112 86 / 0.65);
  border-radius: 4px;
  cursor: pointer;
  box-sizing: border-box;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.btn-recent-chat:hover {
  border-color: var(--pop);
  color: var(--pop);
  background: rgb(224 112 86 / 0.12);
}

.btn-recent-chat:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

.verbal-panel {
  margin-top: clamp(1rem, 3vw, 1.35rem);
  padding: clamp(0.85rem, 2.5vw, 1rem);
  border: 1px dashed rgb(224 112 86 / 0.4);
  border-radius: 4px;
  background: rgb(224 112 86 / 0.06);
  text-align: left;
}

.verbal-panel-title {
  margin: 0 0 0.65rem;
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgb(224 112 86 / 0.95);
}

.verbal-list {
  margin: 0;
  padding: 0 0 0 1.15rem;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.verbal-item {
  margin: 0;
  padding: 0;
  list-style: decimal;
}

.verbal-time {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.625rem;
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.06em;
  color: var(--ink-muted);
  margin-bottom: 0.2rem;
}

.verbal-text {
  margin: 0;
  font-size: clamp(0.8125rem, 0.8rem + 0.15vw, 0.9375rem);
  line-height: 1.5;
  color: var(--ink);
}

.capture-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  margin-bottom: 0.25rem;
  justify-content: center;
  align-items: center;
}

.btn-new-session,
.btn-stop {
  font: inherit;
  cursor: pointer;
  min-height: 2.75rem;
  border-radius: 4px;
  transition:
    background 0.2s ease,
    opacity 0.15s ease,
    border-color 0.2s ease,
    color 0.2s ease,
    transform 0.15s ease;
}

/* Same look as hero `cta-mojo` — dashed outline, pop on hover */
.btn-new-session {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: min(100%, 22rem);
  padding: 0.65rem 1.15rem;
  font-family: var(--font-display);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--ink);
  background: var(--surface-faint);
  border: 1px dashed rgb(224 112 86 / 0.55);
}

.btn-new-session:hover:not(:disabled) {
  border-color: var(--pop);
  color: var(--pop);
  background: rgb(224 112 86 / 0.12);
}

.btn-new-session:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-new-session:focus-visible,
.btn-stop:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

.btn-stop {
  flex: 1 1 10rem;
  padding: 0.55rem 1.15rem;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.15vw, 0.75rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink);
  background: rgb(224 112 86 / 0.08);
  border: 1px dashed rgb(224 112 86 / 0.45);
}

.btn-stop:hover:not(:disabled) {
  background: rgb(224 112 86 / 0.16);
  border-color: var(--pop);
  color: var(--pop);
}

.btn-stop:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.capture-error {
  margin: 0 0 1rem;
  font-size: clamp(0.8125rem, 0.8rem + 0.15vw, 0.875rem);
  color: var(--danger);
}

.upload-status {
  margin: 0 0 1rem;
  font-size: clamp(0.8125rem, 0.8rem + 0.15vw, 0.875rem);
  color: var(--ink-muted);
  word-break: break-word;
}

.upload-status.ok {
  color: var(--success);
}

.preview-wrap {
  position: relative;
  width: 100%;
  max-width: 100%;
  border-radius: 4px;
  overflow: hidden;
  background: var(--void);
  aspect-ratio: 16 / 10;
  border: 1px solid var(--line);
}

.frame-guide {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: clamp(0.4rem, 2.5vw, 1rem);
  pointer-events: none;
}

.frame-guide-target {
  position: relative;
  width: min(92%, calc(100% - 0.75rem));
  aspect-ratio: 4 / 3;
  max-height: min(80%, 42vh);
  border: 2px solid var(--frame-accent);
  border-radius: clamp(3px, 0.8vw, 6px);
  box-shadow: 0 0 0 9999px rgb(0 0 0 / 0.55);
}

.frame-corner {
  position: absolute;
  width: min(14%, 2rem);
  height: min(14%, 2rem);
  border: 0 solid var(--frame-accent);
  pointer-events: none;
}

.frame-corner--tl {
  top: 5px;
  left: 5px;
  border-top-width: 3px;
  border-left-width: 3px;
  border-radius: 2px 0 0 0;
}

.frame-corner--tr {
  top: 5px;
  right: 5px;
  border-top-width: 3px;
  border-right-width: 3px;
  border-radius: 0 2px 0 0;
}

.frame-corner--bl {
  bottom: 5px;
  left: 5px;
  border-bottom-width: 3px;
  border-left-width: 3px;
  border-radius: 0 0 0 2px;
}

.frame-corner--br {
  bottom: 5px;
  right: 5px;
  border-bottom-width: 3px;
  border-right-width: 3px;
  border-radius: 0 0 2px 0;
}

.timer-chip {
  position: absolute;
  top: clamp(0.45rem, 2vw, 0.8rem);
  right: clamp(0.45rem, 2vw, 0.8rem);
  z-index: 2;
  min-height: 2.25rem;
  display: inline-flex;
  align-items: center;
  padding: 0.38rem 0.6rem;
  font-family: var(--font-mono);
  font-size: clamp(0.75rem, 2.8vw, 0.9375rem);
  font-weight: var(--font-mono-weight);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.05em;
  color: var(--ink);
  background: var(--chip-warm-bg);
  border: 1px solid var(--chip-warm-border);
  border-radius: 4px;
  box-shadow: 0 4px 16px rgb(0 0 0 / 0.4);
}

.stat-timer {
  font-family: var(--font-mono);
  font-weight: var(--font-mono-weight);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
}

.preview-video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.recording-badge {
  position: absolute;
  top: clamp(0.5rem, 2vw, 0.75rem);
  left: clamp(0.5rem, 2vw, 0.75rem);
  z-index: 2;
  margin: 0;
  padding: 0.3rem 0.55rem;
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 2vw, 0.625rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #f7f4ee;
  background: rgb(180 60 60 / 0.92);
  border-radius: 2px;
}

@media (max-width: 480px) {
  .capture-actions {
    flex-direction: column;
  }

  .btn-new-session,
  .btn-stop,
  .btn-start {
    flex: 1 1 auto;
    width: 100%;
  }
}

@media (min-width: 600px) {
  .capture-actions {
    flex-wrap: nowrap;
  }

  .btn-new-session,
  .btn-stop,
  .btn-start {
    flex: 0 1 auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn-new-session:hover:not(:disabled),
  .btn-stop:hover:not(:disabled),
  .btn-start:hover:not(:disabled) {
    transform: none;
  }
}
</style>

<style>
/* Unscoped — these styles target teleported DOM outside the component */

.camera-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  background: var(--void, #0a0a0a);
}

.camera-close {
  position: absolute;
  top: clamp(0.75rem, 2vw, 1.25rem);
  right: clamp(0.75rem, 2vw, 1.25rem);
  z-index: 110;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  padding: 0;
  font-size: 1.75rem;
  line-height: 1;
  color: var(--overlay-control-fg);
  background: rgb(0 0 0 / 0.5);
  border: 1px solid var(--overlay-control-border);
  border-radius: 50%;
  cursor: pointer;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: background 0.15s ease;
}

.camera-close:hover {
  background: rgb(0 0 0 / 0.7);
}

.camera-close:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

.camera-error {
  position: absolute;
  top: clamp(0.75rem, 2vw, 1.25rem);
  left: clamp(0.75rem, 2vw, 1.25rem);
  z-index: 105;
  margin: 0;
  padding: 0.5rem 0.75rem;
  font-size: clamp(0.8125rem, 0.8rem + 0.15vw, 0.875rem);
  color: var(--danger, #f87171);
  background: rgb(0 0 0 / 0.6);
  border-radius: 4px;
}

.camera-preview {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.camera-video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.camera-bottom {
  display: flex;
  justify-content: center;
  padding: clamp(0.75rem, 2vw, 1.25rem);
  background: rgb(0 0 0 / 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.camera-bottom .btn-stop {
  flex: 0 0 auto;
  min-width: 10rem;
  font: inherit;
  cursor: pointer;
  min-height: 2.75rem;
  padding: 0.55rem 1.15rem;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.15vw, 0.75rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink);
  background: rgb(224 112 86 / 0.12);
  border: 1px dashed rgb(224 112 86 / 0.5);
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}

.camera-bottom .btn-stop:hover:not(:disabled) {
  background: rgb(224 112 86 / 0.22);
  border-color: var(--pop, #e07056);
  color: var(--pop, #e07056);
}

.camera-bottom .btn-stop:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.camera-bottom .btn-start {
  flex: 0 0 auto;
  min-width: 10rem;
  font: inherit;
  cursor: pointer;
  min-height: 2.75rem;
  padding: 0.55rem 1.15rem;
  border-radius: 4px;
  font-family: var(--font-display, "Syne", system-ui, sans-serif);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--ink, #e8ebe7);
  background: var(--surface-faint);
  border: 1px dashed rgb(224 112 86 / 0.55);
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;
}

.camera-bottom .btn-start:hover:not(:disabled) {
  border-color: var(--pop, #e07056);
  color: var(--pop, #e07056);
  background: rgb(224 112 86 / 0.12);
}

.camera-bottom .btn-start:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.camera-bottom .btn-start:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

.camera-overlay .frame-guide {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.camera-overlay .frame-crop-box {
  position: absolute;
  box-sizing: border-box;
  box-shadow: 0 0 0 9999px rgb(0 0 0 / 0.55);
  border: 2px solid rgb(224 112 86 / 0.92);
  border-radius: clamp(3px, 0.8vw, 6px);
  pointer-events: auto;
  touch-action: none;
  transition: border-color 0.35s ease;
}

.camera-overlay .frame-crop-box.frame-crop-box--locked {
  pointer-events: none;
  touch-action: auto;
  cursor: default;
}

.camera-overlay .frame-crop-box.frame-crop-box--process-ok {
  border-color: rgb(74 222 128 / 0.95);
}

.camera-overlay .frame-crop-box.frame-crop-box--process-err {
  border-color: rgb(248 113 113 / 0.95);
}

/* Inner L-corners — same look as the original static frame */
.camera-overlay .frame-corner-decor {
  position: absolute;
  z-index: 0;
  width: min(14%, 2rem);
  height: min(14%, 2rem);
  border: 0 solid rgb(224 112 86 / 0.95);
  pointer-events: none;
  transition: border-color 0.35s ease;
}

.camera-overlay .frame-crop-box.frame-crop-box--process-ok .frame-corner-decor {
  border-color: rgb(74 222 128 / 0.95);
}

.camera-overlay .frame-crop-box.frame-crop-box--process-err .frame-corner-decor {
  border-color: rgb(248 113 113 / 0.95);
}

.camera-overlay .frame-corner-decor--tl {
  top: 5px;
  left: 5px;
  border-top-width: 3px;
  border-left-width: 3px;
  border-radius: 2px 0 0 0;
}

.camera-overlay .frame-corner-decor--tr {
  top: 5px;
  right: 5px;
  border-top-width: 3px;
  border-right-width: 3px;
  border-radius: 0 2px 0 0;
}

.camera-overlay .frame-corner-decor--bl {
  bottom: 5px;
  left: 5px;
  border-bottom-width: 3px;
  border-left-width: 3px;
  border-radius: 0 0 0 2px;
}

.camera-overlay .frame-corner-decor--br {
  bottom: 5px;
  right: 5px;
  border-bottom-width: 3px;
  border-right-width: 3px;
  border-radius: 0 0 2px 0;
}

.camera-overlay .frame-move {
  position: absolute;
  inset: 18px;
  z-index: 1;
  cursor: move;
  border-radius: 2px;
}

/* Invisible hit targets — resize behavior unchanged */
.camera-overlay .frame-handle {
  position: absolute;
  z-index: 2;
  width: 20px;
  height: 20px;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 2px;
  background: transparent;
  cursor: inherit;
  touch-action: none;
}

.camera-overlay .frame-handle--nw {
  top: -10px;
  left: -10px;
  cursor: nwse-resize;
}
.camera-overlay .frame-handle--n {
  top: -10px;
  left: 50%;
  transform: translateX(-50%);
  cursor: ns-resize;
}
.camera-overlay .frame-handle--ne {
  top: -10px;
  right: -10px;
  cursor: nesw-resize;
}
.camera-overlay .frame-handle--e {
  top: 50%;
  right: -10px;
  transform: translateY(-50%);
  cursor: ew-resize;
}
.camera-overlay .frame-handle--se {
  bottom: -10px;
  right: -10px;
  cursor: nwse-resize;
}
.camera-overlay .frame-handle--s {
  bottom: -10px;
  left: 50%;
  transform: translateX(-50%);
  cursor: ns-resize;
}
.camera-overlay .frame-handle--sw {
  bottom: -10px;
  left: -10px;
  cursor: nesw-resize;
}
.camera-overlay .frame-handle--w {
  top: 50%;
  left: -10px;
  transform: translateY(-50%);
  cursor: ew-resize;
}

.camera-overlay .live-timer-cluster {
  position: absolute;
  top: clamp(0.45rem, 2vw, 0.85rem);
  left: 50%;
  transform: translateX(-50%);
  z-index: 4;
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  max-width: calc(100% - 2rem);
  pointer-events: none;
}

.camera-overlay .live-timer-cluster .recording-badge {
  position: static;
  margin: 0;
  padding: 0.3rem 0.55rem;
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 2vw, 0.625rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--overlay-control-fg);
  background: rgb(224 112 86 / 0.35);
  border: 1px solid rgb(224 112 86 / 0.55);
  border-radius: 2px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  text-shadow: 0 1px 3px rgb(0 0 0 / 0.65);
}

.camera-overlay .live-timer-cluster .timer-chip {
  position: static;
  min-height: 2.25rem;
  display: inline-flex;
  align-items: center;
  padding: 0.38rem 0.6rem;
  font-family: var(--font-mono);
  font-size: clamp(0.75rem, 2.8vw, 0.9375rem);
  font-weight: var(--font-mono-weight);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.05em;
  color: var(--overlay-control-fg);
  background: rgb(224 112 86 / 0.22);
  border: 1px solid rgb(224 112 86 / 0.45);
  border-radius: 4px;
  box-shadow: none;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  text-shadow: 0 1px 3px rgb(0 0 0 / 0.65);
}

.camera-overlay .camera-working-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.32rem 0.65rem;
  font-size: clamp(0.6875rem, 2vw, 0.8125rem);
  font-weight: 500;
  letter-spacing: 0.02em;
  color: #ecfdf5;
  background: rgb(16 185 129 / 0.35);
  border: 1px solid rgb(52 211 153 / 0.55);
  border-radius: 999px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  text-shadow: 0 1px 2px rgb(0 0 0 / 0.5);
}

.camera-overlay .camera-working-dot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 0 0 rgb(52 211 153 / 0.55);
  animation: camera-working-pulse 1.1s ease-out infinite;
}

@keyframes camera-working-pulse {
  0% {
    opacity: 1;
    box-shadow: 0 0 0 0 rgb(52 211 153 / 0.55);
  }
  70% {
    opacity: 0.85;
    box-shadow: 0 0 0 6px rgb(52 211 153 / 0);
  }
  100% {
    opacity: 1;
    box-shadow: 0 0 0 0 rgb(52 211 153 / 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .camera-overlay .camera-working-dot {
    animation: none;
    opacity: 1;
  }
}

.camera-capture-error {
  position: absolute;
  bottom: clamp(7rem, 18vh, 9rem);
  left: 50%;
  transform: translateX(-50%);
  z-index: 106;
  max-width: min(90vw, 24rem);
  margin: 0;
  padding: 0.4rem 0.65rem;
  font-size: clamp(0.75rem, 2.2vw, 0.8125rem);
  color: #fecaca;
  background: rgb(0 0 0 / 0.55);
  border-radius: 4px;
  text-align: center;
}

.camera-session-status {
  position: absolute;
  bottom: clamp(9.25rem, 22vh, 11rem);
  left: 50%;
  transform: translateX(-50%);
  z-index: 105;
  max-width: min(94vw, 28rem);
  margin: 0;
  padding: 0.35rem 0.6rem;
  font-size: clamp(0.6875rem, 1.9vw, 0.75rem);
  line-height: 1.35;
  color: #d1fae5;
  background: rgb(0 0 0 / 0.5);
  border-radius: 4px;
  text-align: center;
}

@media (prefers-reduced-motion: reduce) {
  .camera-close:hover {
    transition: none;
  }
}
</style>

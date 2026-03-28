<script setup lang="ts">
import { ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { useWhiteboardSession } from "../composables/useWhiteboardSession";
import type { PastSessionSummary } from "../types/pastSession";

/** Assign from API / store when ready, e.g. pastSessions.value = await fetchHistory() */
const pastSessions = ref<PastSessionSummary[]>([]);

const {
  videoRef,
  activeStream,
  isSettingUp,
  isSessionActive,
  errorMessage,
  uploadMessage,
  uploadOk,
  uploadState,
  sessionPlaybackUrl,
  streamWsConnected,
  chunksSentCount,
  sessionTimeLabel,
  startSession,
  stopSession,
} = useWhiteboardSession();

const router = useRouter();
const cameraOpen = ref(false);

function handleSetup() {
  cameraOpen.value = true;
  startSession();
}

function handleClose() {
  stopSession();
  cameraOpen.value = false;
}
</script>

<template>
  <div class="dashboard">
    <div class="dashboard-inner">
      <h1 class="dashboard-title">
        Practice session
      </h1>

      <section
        class="capture"
        aria-labelledby="capture-title"
      >
        <h2
          id="capture-title"
          class="capture-title"
        >
          Whiteboard capture
        </h2>
        <p class="capture-hint">
          Setup asks for camera and microphone. Prefer the rear/environment camera on
          a phone. Use the frame overlay to align the board. The timer runs while the
          session is live. Stop flushes the recorder and closes the stream—see README
          for the WebSocket contract your backend should implement.
        </p>

        <div class="capture-actions">
          <button
            type="button"
            class="btn-setup"
            :disabled="isSettingUp || isSessionActive"
            @click="handleSetup"
          >
            {{ isSettingUp ? "Opening camera…" : "Setup" }}
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
          v-if="sessionPlaybackUrl"
          class="playback"
        >
          <p class="playback-label">
            Local replay (same WebM the browser recorded)
          </p>
          <video
            class="playback-video"
            controls
            playsinline
            :src="sessionPlaybackUrl"
          />
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

        <div
          v-if="isSessionActive"
          class="camera-stats"
          aria-live="polite"
        >
          <span class="stat">Stream: {{ streamWsConnected ? "connected" : "…" }}</span>
          <span class="stats-sep" aria-hidden="true">·</span>
          <span class="stat">Chunks sent: {{ chunksSentCount }}</span>
        </div>

        <div
          v-show="activeStream"
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
            <div class="frame-guide-target">
              <span class="frame-corner frame-corner--tl" />
              <span class="frame-corner frame-corner--tr" />
              <span class="frame-corner frame-corner--bl" />
              <span class="frame-corner frame-corner--br" />
            </div>
            <p class="frame-guide-caption">
              Fit whiteboard inside frame
            </p>
          </div>
          <div
            v-if="isSessionActive"
            class="timer-chip"
            role="status"
            :aria-label="`Elapsed ${sessionTimeLabel}`"
          >
            {{ sessionTimeLabel }}
          </div>
          <p
            v-if="isSessionActive"
            class="recording-badge"
          >
            Live
          </p>
        </div>

        <div class="camera-bottom">
          <button
            type="button"
            class="btn-stop"
            :disabled="!isSessionActive"
            @click="handleClose"
          >
            Stop session
          </button>
        </div>
      </div>
    </Teleport>
      </section>

      <section
        class="sessions-section"
        aria-labelledby="sessions-heading"
      >
        <h2
          id="sessions-heading"
          class="sessions-title"
        >
          Previous sessions
        </h2>
        <p class="sessions-intro">
          When recording and backend processing are wired up, push completed sessions
          into <code class="sessions-code">pastSessions</code> (see
          <code class="sessions-code">src/types/pastSession.ts</code>). Each row can
          mount analysis and feedback UI in the slots below—empty bodies are
          intentional until you plug in presenters.
        </p>
        <ul
          v-if="pastSessions.length > 0"
          class="sessions-list"
        >
          <li
            v-for="session in pastSessions"
            :key="session.id"
            class="session-card"
          >
            <div class="session-card-head">
              <span class="session-primary">{{ session.title ?? session.id }}</span>
              <time
                v-if="session.recordedAt"
                class="session-time"
                :datetime="session.recordedAt"
              >{{ session.recordedAt }}</time>
            </div>
            <section
              v-if="session.analysis != null"
              class="session-slot"
              :aria-label="`Analysis for session ${session.id}`"
            >
              <h3 class="session-slot-title">
                Analysis
              </h3>
              <div
                class="session-slot-body"
                data-mount="session-analysis"
              />
            </section>
            <section
              v-if="session.feedback != null"
              class="session-slot"
              :aria-label="`Feedback for session ${session.id}`"
            >
              <h3 class="session-slot-title">
                Feedback
              </h3>
              <div
                class="session-slot-body"
                data-mount="session-feedback"
              />
            </section>
          </li>
        </ul>
        <p
          v-else
          class="sessions-empty"
        >
          No sessions loaded yet.
        </p>

        <button
          type="button"
          class="btn-chat"
          @click="router.push({ name: 'chat' })"
        >
          Open chat
        </button>
      </section>

      <RouterLink
        to="/"
        class="back-link"
      >
        ← Back to home
      </RouterLink>
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
}

.dashboard-title {
  margin: 0 0 clamp(1rem, 3vw, 1.5rem);
  font-family: var(--font-display);
  font-size: clamp(1.65rem, 4vw + 0.5rem, 2.35rem);
  font-weight: 700;
  color: var(--ink);
  letter-spacing: -0.03em;
  line-height: 1.1;
  text-align: left;
}

.capture {
  margin: 0 0 clamp(1.5rem, 4vw, 2rem);
  padding: clamp(1.1rem, 3.5vw, 1.35rem) clamp(1rem, 3.5vw, 1.35rem) clamp(1.25rem, 3.5vw, 1.5rem);
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  background-color: var(--bg-elevated);
  box-shadow:
    0 1px 0 rgb(255 255 255 / 0.05) inset,
    0 24px 48px -32px rgb(0 0 0 / 0.5);
}

.sessions-section {
  margin: 0 0 clamp(1.5rem, 4vw, 2rem);
  padding: clamp(1.1rem, 3.5vw, 1.35rem) clamp(1rem, 3.5vw, 1.35rem) clamp(1.25rem, 3.5vw, 1.5rem);
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  background-color: var(--bg-elevated);
  box-shadow:
    0 1px 0 rgb(255 255 255 / 0.05) inset,
    0 24px 48px -32px rgb(0 0 0 / 0.5);
}

.sessions-title {
  margin: 0 0 0.5rem;
  font-size: clamp(1rem, 0.95rem + 0.3vw, 1.1rem);
  font-weight: 600;
  color: var(--ink);
}

.sessions-intro {
  margin: 0 0 clamp(1rem, 3vw, 1.25rem);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  line-height: 1.55;
  color: var(--ink-muted);
}

.sessions-code {
  font-family: var(--font-mono);
  font-size: 0.8em;
  padding: 0.1em 0.35em;
  border-radius: 3px;
  background: rgb(255 255 255 / 0.06);
  border: 1px solid var(--line);
  word-break: break-all;
}

.sessions-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: clamp(0.75rem, 2vw, 1rem);
}

.session-card {
  margin: 0;
  padding: clamp(0.85rem, 2.5vw, 1rem);
  border: 1px solid var(--line);
  border-radius: 4px;
  background-color: var(--bg-soft);
}

.session-card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.35rem 1rem;
  margin-bottom: 0.65rem;
}

.session-primary {
  font-family: var(--font-display);
  font-size: clamp(0.9375rem, 0.9rem + 0.2vw, 1.0625rem);
  font-weight: 600;
  color: var(--ink);
  word-break: break-word;
}

.session-time {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  letter-spacing: 0.04em;
  color: var(--ink-muted);
}

.session-slot {
  margin-top: 0.65rem;
  padding-top: 0.65rem;
  border-top: 1px solid var(--line);
}

.session-slot-title {
  margin: 0 0 0.4rem;
  font-family: var(--font-mono);
  font-size: 0.625rem;
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.session-slot-body {
  min-height: 2.5rem;
  border-radius: 3px;
  border: 1px dashed var(--line-strong);
  background: rgb(0 0 0 / 0.15);
}

.btn-chat {
  margin-top: clamp(1rem, 3vw, 1.25rem);
  min-height: 2.75rem;
  width: 100%;
  padding: 0.55rem 1.15rem;
  font-family: var(--font-sans);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
  background: rgb(255 255 255 / 0.04);
  border: 1px dashed var(--line-strong);
  border-radius: 4px;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}

.btn-chat:hover:not(:disabled) {
  background: var(--accent-soft);
  border-color: var(--accent);
}

.btn-chat:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-chat:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

.sessions-empty {
  margin: 0;
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  color: var(--ink-muted);
  line-height: 1.55;
}

.capture-title {
  margin: 0 0 0.5rem;
  font-size: clamp(1rem, 0.95rem + 0.3vw, 1.1rem);
  font-weight: 600;
  color: var(--ink);
}

.capture-hint {
  margin: 0 0 clamp(1rem, 3vw, 1.25rem);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  line-height: 1.55;
  color: var(--ink-muted);
}

.capture-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  margin-bottom: 1rem;
}

.session-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 0.5rem;
  margin: 0 0 0.85rem;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.2vw, 0.8125rem);
  color: var(--ink-muted);
  line-height: 1.4;
}

.stat {
  min-width: 0;
}

.stats-sep {
  color: var(--line-strong);
}

.btn-setup,
.btn-stop {
  font: inherit;
  cursor: pointer;
  min-height: 2.75rem;
  padding: 0.55rem 1.15rem;
  border-radius: 4px;
  transition:
    background 0.15s ease,
    opacity 0.15s ease,
    border-color 0.15s ease,
    transform 0.15s ease;
}

.btn-setup {
  flex: 1 1 10rem;
  font-family: var(--font-sans);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--void);
  background: var(--ink);
  border: 1px solid rgb(255 255 255 / 0.12);
}

.btn-setup:hover:not(:disabled) {
  background: #f2f5f1;
  border-color: rgb(255 255 255 / 0.2);
}

.btn-setup:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-setup:focus-visible,
.btn-stop:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

.btn-stop {
  flex: 1 1 10rem;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.15vw, 0.75rem);
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink);
  background: rgb(255 255 255 / 0.04);
  border: 1px solid var(--line-strong);
}

.btn-stop:hover:not(:disabled) {
  background: var(--accent-soft);
  border-color: var(--accent);
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
  border: 2px solid rgb(255 255 255 / 0.9);
  border-radius: clamp(3px, 0.8vw, 6px);
  box-shadow: 0 0 0 9999px rgb(0 0 0 / 0.55);
}

.frame-corner {
  position: absolute;
  width: min(14%, 2rem);
  height: min(14%, 2rem);
  border: 0 solid rgb(255 255 255 / 0.95);
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

.frame-guide-caption {
  position: absolute;
  bottom: clamp(5%, 3vw, 11%);
  left: 50%;
  transform: translateX(-50%);
  width: min(95%, 18rem);
  margin: 0;
  text-align: center;
  font-family: var(--font-mono);
  font-size: clamp(0.5rem, 2.2vw, 0.6875rem);
  font-weight: 500;
  letter-spacing: 0.1em;
  line-height: 1.35;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.94);
  text-shadow:
    0 0 8px rgb(0 0 0 / 0.9),
    0 1px 2px rgb(0 0 0 / 0.8);
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
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.05em;
  color: var(--void);
  background: rgb(255 252 248 / 0.95);
  border: 1px solid rgb(255 255 255 / 0.35);
  border-radius: 4px;
  box-shadow: 0 4px 16px rgb(0 0 0 / 0.4);
}

.stat-timer {
  font-family: var(--font-mono);
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
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #f7f4ee;
  background: rgb(180 60 60 / 0.92);
  border-radius: 2px;
}

.playback {
  margin-top: clamp(1rem, 3vw, 1.35rem);
  padding-top: clamp(1rem, 3vw, 1.35rem);
  border-top: 1px solid var(--line);
}

.playback-label {
  margin: 0 0 0.5rem;
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.playback-video {
  display: block;
  width: 100%;
  max-width: min(28rem, 100%);
  max-height: min(50vh, 24rem);
  border-radius: 4px;
  border: 1px solid var(--line);
  background: var(--void);
}

.back-link {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.15vw, 0.75rem);
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-muted);
  text-decoration: none;
}

.back-link:hover {
  color: var(--accent-hover);
  text-decoration: underline;
}

.back-link:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
  border-radius: 2px;
}

@media (max-width: 480px) {
  .capture-actions {
    flex-direction: column;
  }

  .btn-setup,
  .btn-stop {
    flex: 1 1 auto;
    width: 100%;
  }

  .session-stats {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.25rem;
  }

  .stats-sep {
    display: none;
  }

  .timer-chip {
    top: clamp(0.35rem, 1.5vw, 0.55rem);
    right: clamp(0.35rem, 1.5vw, 0.55rem);
    min-height: 2rem;
    padding: 0.3rem 0.5rem;
  }

  .recording-badge {
    top: clamp(0.35rem, 1.5vw, 0.55rem);
    left: clamp(0.35rem, 1.5vw, 0.55rem);
    max-width: calc(100% - 5.5rem);
  }

  .frame-guide-target {
    max-height: min(76%, 36vh);
  }
}

@media (min-width: 600px) {
  .capture-actions {
    flex-wrap: nowrap;
  }

  .btn-setup,
  .btn-stop {
    flex: 0 1 auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn-setup:hover:not(:disabled),
  .btn-stop:hover:not(:disabled) {
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
  color: rgb(255 255 255 / 0.9);
  background: rgb(0 0 0 / 0.5);
  border: 1px solid rgb(255 255 255 / 0.15);
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

.camera-stats {
  position: absolute;
  top: clamp(0.75rem, 2vw, 1.25rem);
  left: clamp(0.75rem, 2vw, 1.25rem);
  z-index: 105;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 0.5rem;
  padding: 0.4rem 0.65rem;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.2vw, 0.8125rem);
  color: rgb(255 255 255 / 0.8);
  background: rgb(0 0 0 / 0.5);
  border-radius: 4px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
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
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink);
  background: rgb(255 255 255 / 0.04);
  border: 1px solid var(--line-strong);
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}

.camera-bottom .btn-stop:hover:not(:disabled) {
  background: var(--accent-soft);
  border-color: var(--accent);
}

.camera-bottom .btn-stop:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.camera-overlay .frame-guide {
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

.camera-overlay .frame-guide-target {
  position: relative;
  width: min(92%, calc(100% - 0.75rem));
  aspect-ratio: 4 / 3;
  max-height: min(80%, 42vh);
  border: 2px solid rgb(255 255 255 / 0.9);
  border-radius: clamp(3px, 0.8vw, 6px);
  box-shadow: 0 0 0 9999px rgb(0 0 0 / 0.55);
}

.camera-overlay .frame-corner {
  position: absolute;
  width: min(14%, 2rem);
  height: min(14%, 2rem);
  border: 0 solid rgb(255 255 255 / 0.95);
  pointer-events: none;
}

.camera-overlay .frame-corner--tl { top: 5px; left: 5px; border-top-width: 3px; border-left-width: 3px; border-radius: 2px 0 0 0; }
.camera-overlay .frame-corner--tr { top: 5px; right: 5px; border-top-width: 3px; border-right-width: 3px; border-radius: 0 2px 0 0; }
.camera-overlay .frame-corner--bl { bottom: 5px; left: 5px; border-bottom-width: 3px; border-left-width: 3px; border-radius: 0 0 0 2px; }
.camera-overlay .frame-corner--br { bottom: 5px; right: 5px; border-bottom-width: 3px; border-right-width: 3px; border-radius: 0 0 2px 0; }

.camera-overlay .frame-guide-caption {
  position: absolute;
  bottom: clamp(5%, 3vw, 11%);
  left: 50%;
  transform: translateX(-50%);
  width: min(95%, 18rem);
  margin: 0;
  text-align: center;
  font-family: var(--font-mono);
  font-size: clamp(0.5rem, 2.2vw, 0.6875rem);
  font-weight: 500;
  letter-spacing: 0.1em;
  line-height: 1.35;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.94);
  text-shadow: 0 0 8px rgb(0 0 0 / 0.9), 0 1px 2px rgb(0 0 0 / 0.8);
}

.camera-overlay .timer-chip {
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
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.05em;
  color: var(--void);
  background: rgb(255 252 248 / 0.95);
  border: 1px solid rgb(255 255 255 / 0.35);
  border-radius: 4px;
  box-shadow: 0 4px 16px rgb(0 0 0 / 0.4);
}

.camera-overlay .recording-badge {
  position: absolute;
  top: clamp(0.5rem, 2vw, 0.75rem);
  left: clamp(0.5rem, 2vw, 0.75rem);
  z-index: 2;
  margin: 0;
  padding: 0.3rem 0.55rem;
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 2vw, 0.625rem);
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #f7f4ee;
  background: rgb(180 60 60 / 0.92);
  border-radius: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .camera-close:hover {
    transition: none;
  }
}
</style>

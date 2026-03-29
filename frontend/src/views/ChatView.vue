<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useMirageAuth } from "../composables/useMirageAuth";
import { useSessionAnalysis } from "../composables/useSessionAnalysis";
import { apiUrl } from "../utils/apiUrl";
import {
  getLastSessionId,
  loadWhiteboardSnapshot,
  type WhiteboardSessionSnapshot,
} from "../utils/sessionOutputStorage";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  displayedText: string;
  streaming: boolean;
}

const SEEDED_ANALYSIS_MESSAGE =
  "Your session has been analyzed. I've reviewed your system design and generated feedback above. Feel free to ask me anything about your architecture - for example, why a certain component was flagged, how to fix a specific gap, or how your design would handle a specific failure scenario.";

const route = useRoute();
const router = useRouter();
const { apiFetch, userId } = useMirageAuth();

const messages = ref<ChatMessage[]>([]);
const input = ref("");
const isStreaming = ref(false);
const messagesEl = ref<HTMLElement | null>(null);
const seededSessionId = ref<string | null>(null);
const mirageSnapshot = ref<WhiteboardSessionSnapshot | null>(null);

const {
  status: analysisStatus,
  stage: analysisStage,
  errorMessage: analysisErrorMessage,
  analysis,
  feedback,
  score,
  startPolling,
  stopPolling,
} = useSessionAnalysis();

const currentUserId = computed(() => userId.value ?? null);

const currentSessionId = computed(() => {
  const paramSessionId = route.params.sessionId;
  if (typeof paramSessionId === "string" && paramSessionId.trim()) {
    return paramSessionId;
  }
  const querySession = route.query.session;
  if (typeof querySession === "string" && querySession.trim()) {
    return querySession;
  }
  return null;
});

const sessionLabel = computed(() => currentSessionId.value);

const analysisHeadline = computed(() => {
  if (!analysis.value) {
    return null;
  }
  return `${analysis.value.architecture_pattern} | ${analysis.value.component_count} components | ${analysis.value.connection_density} connectivity`;
});

const analysisEntryPointLine = computed(() => {
  if (!analysis.value) {
    return null;
  }
  return analysis.value.entry_point
    ? `Entry point: ${analysis.value.entry_point}`
    : "Entry point: not identified";
});

const analysisMissingLine = computed(() => {
  if (!analysis.value) {
    return null;
  }
  const missing = analysis.value.missing_standard_components;
  if (!missing.length) {
    return "Missing: none identified";
  }
  return `Missing: ${missing.join(", ")}`;
});

const feedbackStrengths = computed(() => feedback.value?.strengths ?? []);
const feedbackImprovements = computed(() => feedback.value?.improvements ?? []);
const feedbackCriticalGaps = computed(() => feedback.value?.critical_gaps ?? []);
const feedbackNarrative = computed(
  () => feedback.value?.narrative ?? "No coaching narrative available.",
);

const progressStages = ["queued", "validation", "saving_session", "analysis", "saving_analysis", "complete"] as const;

const progressPercent = computed(() => {
  if (analysisStatus.value === "complete") return 100;
  if (analysisStatus.value === "failed") return 0;
  if (analysisStatus.value !== "processing") return 0;
  const idx = progressStages.indexOf(analysisStage.value as typeof progressStages[number]);
  if (idx < 0) return 5;
  return Math.round(((idx + 1) / progressStages.length) * 100);
});

const progressLabel = computed(() => {
  if (analysisStatus.value === "complete") return "Evaluation complete";
  if (analysisStatus.value === "failed") return "Evaluation failed";
  if (analysisStatus.value !== "processing") return "";
  const labels: Record<string, string> = {
    queued: "Queued",
    validation: "Validating graph",
    saving_session: "Saving session",
    analysis: "Analyzing design",
    saving_analysis: "Saving analysis",
    complete: "Complete",
  };
  return labels[analysisStage.value ?? ""] ?? "Processing";
});

function scoreBar(value: number): string {
  const normalized = Math.min(25, Math.max(0, Math.round(value)));
  return `${"#".repeat(normalized)}${"-".repeat(25 - normalized)}`;
}

const scoreLines = computed(() => {
  if (!score.value) {
    return [];
  }
  return [
    {
      key: "completeness",
      label: "Completeness",
      value: score.value.breakdown.completeness,
      bar: scoreBar(score.value.breakdown.completeness),
    },
    {
      key: "scalability",
      label: "Scalability",
      value: score.value.breakdown.scalability,
      bar: scoreBar(score.value.breakdown.scalability),
    },
    {
      key: "reliability",
      label: "Reliability",
      value: score.value.breakdown.reliability,
      bar: scoreBar(score.value.breakdown.reliability),
    },
    {
      key: "clarity",
      label: "Clarity",
      value: score.value.breakdown.clarity,
      bar: scoreBar(score.value.breakdown.clarity),
    },
  ];
});

function loadMirageSnapshot(sessionId: string | null) {
  const activeUserId = currentUserId.value;
  mirageSnapshot.value =
    sessionId && activeUserId
      ? loadWhiteboardSnapshot(activeUserId, sessionId)
      : null;
}

const localAnalysisDisplay = computed(() => {
  const snapshot = mirageSnapshot.value;
  if (!snapshot) {
    return null;
  }
  const deltas = snapshot.verbalResponses
    .map((item) => item.visualDelta)
    .filter((value): value is string => typeof value === "string" && value.trim().length > 0);
  if (!deltas.length) {
    return "No visual delta text was returned for this session.";
  }
  return deltas.join("\n\n—\n\n");
});

const localFeedbackDisplay = computed(() => {
  const snapshot = mirageSnapshot.value;
  if (!snapshot) {
    return null;
  }
  const responses = snapshot.verbalResponses
    .map((item) => item.verbalResponse)
    .filter((value) => value.trim().length > 0);
  if (!responses.length) {
    return "No coach reply text was captured for this snapshot.";
  }
  return responses.join("\n\n—\n\n");
});

const localScoreDisplay = computed(() => {
  const snapshot = mirageSnapshot.value;
  if (!snapshot) {
    return null;
  }
  const parts = [
    `Stills uploaded (HTTP ok): ${snapshot.imageFramesSentCount}`,
    `Discarded (no change): ${snapshot.discardedFramesCount}`,
    `Processed with reply: ${snapshot.processedFramesCount}`,
  ];
  if (snapshot.uploadMessage) {
    parts.push(snapshot.uploadMessage);
  } else if (snapshot.uploadOk === false) {
    parts.push("Session end reported an error.");
  }
  return parts.join("\n");
});

const chatEmptyMessage = computed(() => {
  if (!currentSessionId.value) {
    return "Open chat from a completed session to ask analysis-aware follow-up questions.";
  }
  return "Ask follow-up questions about this session's architecture, gaps, and tradeoffs.";
});

const outputNote = computed(() => {
  if (!currentSessionId.value) {
    return "Open chat from a completed session to view post-session analysis. Local snapshots saved in this browser also appear here.";
  }
  // Session upload failed — analysis never started, no point polling.
  if (mirageSnapshot.value?.uploadOk === false) {
    const msg =
      mirageSnapshot.value.uploadMessage ?? "Session could not be saved to the server.";
    return `${msg} No analysis is available for this session. Showing local device snapshot only.`;
  }
  if (analysisStatus.value === "processing") {
    const stage = analysisStage.value ? ` (${analysisStage.value})` : "";
    if (mirageSnapshot.value) {
      return `Analysis in progress${stage}. Showing the local browser snapshot until the backend analysis completes.`;
    }
    return `Analysis in progress${stage}. This panel updates automatically.`;
  }
  if (analysisStatus.value === "failed") {
    if (mirageSnapshot.value) {
      const error = analysisErrorMessage.value ?? "Analysis failed.";
      return `${error} Showing the local browser snapshot for this session.`;
    }
    return analysisErrorMessage.value ?? "Analysis failed. Retry the session end flow.";
  }
  if (analysisStatus.value === "complete") {
    return "Analysis complete. Ask follow-up questions in the chat panel.";
  }
  if (mirageSnapshot.value) {
    return "Showing the local browser snapshot saved on this device for this session.";
  }
  return "Waiting for analysis to begin.";
});

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
    }
  });
}

function streamText(msgIndex: number, fullText: string) {
  const chars = Array.from(fullText);
  let i = 0;

  const interval = setInterval(() => {
    if (i < chars.length) {
      const end = Math.min(i + 3, chars.length);
      messages.value[msgIndex].displayedText += chars.slice(i, end).join("");
      i = end;
      scrollToBottom();
    } else {
      messages.value[msgIndex].streaming = false;
      isStreaming.value = false;
      clearInterval(interval);
    }
  }, 30);
}

onMounted(() => {
  if (currentSessionId.value) {
    loadMirageSnapshot(currentSessionId.value);
    return;
  }
  const activeUserId = currentUserId.value;
  if (!activeUserId) {
    return;
  }
  const lastSessionId = getLastSessionId(activeUserId);
  if (!lastSessionId) {
    return;
  }
  void router.replace({
    name: "chat",
    params: { sessionId: lastSessionId },
    query: { session: lastSessionId },
  });
});

async function sendMessage() {
  const text = input.value.trim();
  if (!text || isStreaming.value) {
    return;
  }
  const sessionId = currentSessionId.value;

  messages.value.push(
    reactive({
      role: "user",
      text,
      displayedText: text,
      streaming: false,
    }),
  );
  input.value = "";
  scrollToBottom();

  if (!sessionId) {
    const response = chatEmptyMessage.value;
    messages.value.push(
      reactive({
        role: "assistant",
        text: response,
        displayedText: response,
        streaming: false,
      }),
    );
    scrollToBottom();
    return;
  }

  isStreaming.value = true;
  try {
    const res = await apiFetch(apiUrl("/chat"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: sessionId,
        message: text,
      }),
    });
    const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const response =
      res.ok && typeof payload.response === "string" && payload.response.trim()
        ? payload.response
        : typeof payload.error === "string" && payload.error.trim()
          ? payload.error
          : `Chat request failed (${res.status}).`;

    messages.value.push(
      reactive({
        role: "assistant",
        text: response,
        displayedText: "",
        streaming: true,
      }),
    );
    scrollToBottom();
    streamText(messages.value.length - 1, response);
  } catch {
    const response = "Could not reach the chat service.";
    messages.value.push(
      reactive({
        role: "assistant",
        text: response,
        displayedText: "",
        streaming: true,
      }),
    );
    scrollToBottom();
    streamText(messages.value.length - 1, response);
  }
}

watch(
  [currentSessionId, currentUserId],
  ([nextSessionId, nextUserId], [previousSessionId, previousUserId]) => {
    if (nextUserId !== previousUserId) {
      loadMirageSnapshot(nextSessionId);
    }

    if (nextSessionId !== previousSessionId) {
      messages.value = [];
      seededSessionId.value = null;
      input.value = "";
    }

    loadMirageSnapshot(nextSessionId);

    if (nextSessionId) {
      // Don't poll if the local snapshot already tells us the upload failed.
      // The server never created an analysis job for this session, so polling
      // would immediately 404 and show a confusing "unknown session" error.
      if (mirageSnapshot.value?.uploadOk === false) {
        stopPolling();
        return;
      }
      startPolling(nextSessionId);
      return;
    }
    stopPolling();
  },
  { immediate: true },
);

watch([analysisStatus, currentSessionId], ([nextStatus, nextSessionId]) => {
  if (nextStatus !== "complete" || !nextSessionId) {
    return;
  }
  if (seededSessionId.value === nextSessionId) {
    return;
  }
  seededSessionId.value = nextSessionId;
  messages.value.push(
    reactive({
      role: "assistant",
      text: SEEDED_ANALYSIS_MESSAGE,
      displayedText: SEEDED_ANALYSIS_MESSAGE,
      streaming: false,
    }),
  );
  scrollToBottom();
});
</script>

<template>
  <div class="chat-page">
    <section class="output-side" aria-labelledby="chat-mirage-title">
      <h2 id="chat-mirage-title" class="side-heading side-heading--mirage">
        Mirage
      </h2>

      <div
        v-if="progressPercent > 0 || analysisStatus === 'failed'"
        class="progress-wrapper"
      >
        <div class="progress-track">
          <div
            class="progress-fill"
            :class="{ 'progress-fill--failed': analysisStatus === 'failed', 'progress-fill--complete': analysisStatus === 'complete' }"
            :style="{ width: analysisStatus === 'failed' ? '100%' : `${progressPercent}%` }"
          />
        </div>
        <span class="progress-text">{{ progressLabel }}</span>
      </div>

      <div class="output-body">
        <!-- Waiting / no session state -->
        <div v-if="!currentSessionId && !mirageSnapshot" class="output-empty">
          <p class="output-empty-text">{{ outputNote }}</p>
        </div>

        <!-- Processing state -->
        <div v-else-if="analysisStatus === 'processing' && !localAnalysisDisplay" class="output-empty">
          <p class="output-empty-text">{{ outputNote }}</p>
        </div>

        <!-- Failed state -->
        <div v-else-if="analysisStatus === 'failed' && !localAnalysisDisplay" class="output-empty">
          <p class="output-error">{{ analysisErrorMessage ?? "Evaluation failed." }}</p>
          <p class="output-note">{{ outputNote }}</p>
        </div>

        <!-- Evaluation content -->
        <template v-else>
          <!-- Score banner -->
          <div v-if="analysisStatus === 'complete' && score" class="eval-score-banner">
            <span class="eval-score-grade">{{ score.grade }}</span>
            <span class="eval-score-total">{{ score.total }}<span class="eval-score-max"> / 100</span></span>
          </div>

          <!-- Score breakdown -->
          <div v-if="analysisStatus === 'complete' && score" class="eval-breakdown">
            <div v-for="line in scoreLines" :key="line.key" class="eval-bar-row">
              <span class="eval-bar-label">{{ line.label }}</span>
              <div class="eval-bar-track">
                <div class="eval-bar-fill" :style="{ width: `${(line.value / 25) * 100}%` }" />
              </div>
              <span class="eval-bar-value">{{ line.value }}</span>
            </div>
          </div>
          <div v-else-if="localScoreDisplay" class="eval-local-score">
            <p class="output-detail">{{ localScoreDisplay }}</p>
          </div>

          <!-- Analysis summary -->
          <div v-if="analysisStatus === 'complete' && analysis" class="eval-section">
            <p class="eval-headline">{{ analysisHeadline }}</p>
            <p class="eval-meta">{{ analysisEntryPointLine }}</p>
            <p class="eval-meta">{{ analysisMissingLine }}</p>
            <p class="eval-body">{{ analysis.summary }}</p>
          </div>
          <div v-else-if="localAnalysisDisplay" class="eval-section">
            <p class="eval-body">{{ localAnalysisDisplay }}</p>
          </div>

          <!-- Strengths -->
          <div v-if="analysisStatus === 'complete' && feedback" class="eval-section">
            <p class="eval-section-label">Strengths</p>
            <ul class="eval-list">
              <li v-for="item in feedbackStrengths" :key="`s-${item}`">{{ item }}</li>
              <li v-if="feedbackStrengths.length === 0" class="eval-list-empty">None identified</li>
            </ul>
          </div>

          <!-- Improvements -->
          <div v-if="analysisStatus === 'complete' && feedback" class="eval-section">
            <p class="eval-section-label">Improvements</p>
            <ul class="eval-list">
              <li v-for="item in feedbackImprovements" :key="`i-${item}`">{{ item }}</li>
              <li v-if="feedbackImprovements.length === 0" class="eval-list-empty">None identified</li>
            </ul>
          </div>

          <!-- Critical gaps -->
          <div v-if="analysisStatus === 'complete' && feedbackCriticalGaps.length > 0" class="eval-section">
            <p class="eval-section-label eval-section-label--critical">Critical gaps</p>
            <ul class="eval-list eval-list--critical">
              <li v-for="item in feedbackCriticalGaps" :key="`g-${item}`">{{ item }}</li>
            </ul>
          </div>

          <!-- Narrative -->
          <div v-if="analysisStatus === 'complete' && feedback" class="eval-section">
            <p class="eval-body eval-body--narrative">{{ feedbackNarrative }}</p>
          </div>

          <!-- Local feedback fallback -->
          <div v-else-if="localFeedbackDisplay && analysisStatus !== 'complete'" class="eval-section">
            <p class="eval-body">{{ localFeedbackDisplay }}</p>
          </div>

          <p class="output-note">{{ outputNote }}</p>
        </template>
      </div>
    </section>

    <div class="column-divider" aria-hidden="true" />

    <section class="chat-side" aria-labelledby="chat-column-title">
      <h1 id="chat-column-title" class="side-heading side-heading--chat">
        Chat
      </h1>

      <div ref="messagesEl" class="chat-messages">
        <p v-if="messages.length === 0" class="chat-empty">
          {{ chatEmptyMessage }}
        </p>
        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="chat-bubble"
          :class="[msg.role, { streaming: msg.streaming }]"
        >
          <div class="chat-content" :class="{ 'has-speck': msg.role === 'assistant' }">
            <span v-if="msg.role === 'assistant'" class="ai-speck" />
            <p class="chat-text">
              {{ msg.displayedText }}<span v-if="msg.streaming" class="cursor" />
            </p>
          </div>
        </div>
      </div>

      <form class="chat-input-bar" @submit.prevent="sendMessage">
        <input
          v-model="input"
          class="chat-input"
          type="text"
          aria-label="Message to agent"
          placeholder="Ask about this session..."
          :disabled="isStreaming"
          autocomplete="off"
        />
        <button type="submit" class="btn-send" :disabled="!input.trim() || isStreaming">
          Send
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.chat-page {
  width: 100%;
  min-height: calc(100dvh - 2 * var(--page-pad-y, 1.25rem));
  margin: calc(-1 * var(--page-pad-y, 1.25rem)) calc(-1 * var(--page-pad-x, 1rem));
  padding: var(--page-pad-y, 1.25rem) var(--page-pad-x, 1rem);
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 0;
  box-sizing: border-box;
}

.chat-side,
.output-side {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

@keyframes side-heading-shine {
  0%,
  100% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
}

.side-heading {
  flex-shrink: 0;
  align-self: flex-start;
  margin: 0 0 0.75rem;
  padding: 0.02em 0;
  font-family: var(--font-display);
  font-size: clamp(1.125rem, 2vw + 0.5rem, 1.5rem);
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.15;
  text-align: left;
}

.side-heading--mirage {
  background: linear-gradient(
    100deg,
    var(--pop) 0%,
    #ff8f78 22%,
    #ffd8ce 45%,
    var(--hero-shimmer-mid) 50%,
    #ffd8ce 55%,
    #ff8f78 78%,
    var(--pop) 100%
  );
  background-size: 220% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: side-heading-shine 3.5s ease-in-out infinite;
}

.side-heading--chat {
  background: linear-gradient(
    100deg,
    var(--accent) 0%,
    var(--accent-hover) 22%,
    #9db8a8 45%,
    #c5ddd0 50%,
    #9db8a8 55%,
    var(--accent-hover) 78%,
    var(--accent) 100%
  );
  background-size: 220% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: side-heading-shine 3.5s ease-in-out infinite;
}

.column-divider {
  flex-shrink: 0;
  width: 1px;
  margin: 0 clamp(0.75rem, 2vw, 1.25rem);
  align-self: stretch;
  background: var(--line);
  opacity: 0.85;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 0.25rem 1rem 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  -webkit-overflow-scrolling: touch;
}

.chat-empty {
  margin: auto;
  padding: 2rem 0;
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  font-weight: 500;
  color: var(--ink-muted);
  text-align: center;
  line-height: 1.55;
  max-width: 28rem;
}

.chat-bubble {
  max-width: min(100%, 42rem);
  padding: 0.35rem 0;
}

.chat-bubble.user {
  align-self: flex-end;
  background: var(--surface-mid);
  border: 1px solid var(--line);
  border-radius: 1.125rem;
  padding: 0.5rem 0.95rem;
}

.chat-bubble.assistant {
  align-self: flex-start;
}

.chat-content {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

.ai-speck {
  flex-shrink: 0;
  width: 0.5rem;
  height: 0.5rem;
  margin-top: 0.45em;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent, #e0704e), var(--pop, #c45a3a));
  box-shadow: 0 0 6px rgb(224 112 78 / 0.4);
}

.chat-bubble.streaming .ai-speck {
  animation: speck-pulse 1.5s ease-in-out infinite;
}

@keyframes speck-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.3);
  }
}

.chat-text {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  font-weight: 500;
  line-height: 1.55;
  color: var(--ink);
  white-space: pre-wrap;
}

.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 1px;
  background: var(--ink);
  vertical-align: text-bottom;
  animation: blink 0.6s step-end infinite;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

.chat-input-bar {
  flex-shrink: 0;
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem 0 0;
  margin-top: auto;
  border-top: 1px solid var(--line);
  background: transparent;
}

.chat-input {
  flex: 1;
  min-height: 2.75rem;
  padding: 0.55rem 0.85rem;
  font-family: var(--font-mono);
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  font-weight: 500;
  color: var(--ink);
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  outline: none;
  transition: border-color 0.15s ease;
}

.chat-input:focus {
  border-color: var(--accent);
}

.chat-input::placeholder {
  color: var(--ink-faint);
}

.btn-send {
  min-height: 2.75rem;
  padding: 0.55rem 1.15rem;
  font-family: var(--font-mono);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--void);
  background: var(--ink);
  border: 1px solid var(--btn-ink-border);
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.btn-send:hover:not(:disabled) {
  background: var(--btn-ink-bg-hover);
  border-color: var(--btn-ink-border-hover);
}

.btn-send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-send:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

/* ---- Progress bar ---- */

.progress-wrapper {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 1rem;
}

.progress-track {
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: var(--surface-mid, #1e1e1e);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--pop, #c45a3a), #ff8f78);
  transition: width 0.6s ease;
}

.progress-fill--complete {
  background: linear-gradient(90deg, var(--accent, #6b9f6b), #9db8a8);
}

.progress-fill--failed {
  background: var(--danger, #e05050);
}

.progress-text {
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.1vw, 0.625rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

/* ---- Output body ---- */

.output-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 0.5rem 1.5rem 0;
  display: flex;
  flex-direction: column;
  gap: clamp(1rem, 2.5vw, 1.5rem);
  -webkit-overflow-scrolling: touch;
}

.output-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 2rem 1rem;
}

.output-empty-text {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  font-weight: 500;
  color: var(--ink-muted);
  text-align: center;
  line-height: 1.55;
  max-width: 28rem;
}

.output-error {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.15vw, 0.875rem);
  color: var(--danger);
  text-align: center;
}

.output-detail {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  font-weight: 500;
  line-height: 1.55;
  color: var(--ink);
  white-space: pre-wrap;
}

.output-note {
  margin: auto 0 0;
  padding-top: 1rem;
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.1vw, 0.625rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.08em;
  color: var(--ink-faint);
  text-align: left;
  line-height: 1.45;
}

/* ---- Score banner ---- */

.eval-score-banner {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  background: var(--surface-mid, #1e1e1e);
  border: 1px solid var(--line);
}

.eval-score-grade {
  font-family: var(--font-display);
  font-size: clamp(1.75rem, 3vw + 0.5rem, 2.5rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1;
  background: linear-gradient(100deg, var(--pop) 0%, #ff8f78 50%, #ffd8ce 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.eval-score-total {
  font-family: var(--font-mono);
  font-size: clamp(1rem, 1.5vw + 0.25rem, 1.25rem);
  font-weight: 600;
  color: var(--ink);
}

.eval-score-max {
  font-weight: 400;
  color: var(--ink-muted);
}

/* ---- Score breakdown bars ---- */

.eval-breakdown {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.eval-bar-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.eval-bar-label {
  flex-shrink: 0;
  width: 6.5rem;
  font-family: var(--font-mono);
  font-size: clamp(0.625rem, 0.6rem + 0.15vw, 0.6875rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.eval-bar-track {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--surface-mid, #1e1e1e);
  overflow: hidden;
}

.eval-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--pop, #c45a3a), #ff8f78);
  transition: width 0.5s ease;
}

.eval-bar-value {
  flex-shrink: 0;
  width: 1.75rem;
  text-align: right;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.15vw, 0.75rem);
  font-weight: 600;
  color: var(--ink);
}

.eval-local-score {
  padding: 0.5rem 0;
}

/* ---- Evaluation sections ---- */

.eval-section {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.eval-headline {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  font-weight: 600;
  line-height: 1.45;
  color: var(--ink);
}

.eval-meta {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 500;
  line-height: 1.45;
  color: var(--ink-muted);
}

.eval-body {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  font-weight: 500;
  line-height: 1.6;
  color: var(--ink);
  white-space: pre-wrap;
}

.eval-body--narrative {
  padding: 0.6rem 0.85rem;
  border-left: 2px solid var(--line-strong, #444);
  color: var(--ink-muted);
  font-style: italic;
}

.eval-section-label {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.625rem, 0.6rem + 0.15vw, 0.6875rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.eval-section-label--critical {
  color: var(--danger);
}

.eval-list {
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  line-height: 1.5;
}

.eval-list-empty {
  color: var(--ink-muted);
  font-style: italic;
}

.eval-list--critical {
  color: var(--danger);
}

@media (max-width: 768px) {
  .chat-page {
    flex-direction: column;
    min-height: calc(100dvh - 2 * var(--page-pad-y, 1.25rem));
  }

  .output-side {
    order: 3;
    flex: 1;
    min-height: 12rem;
  }

  .column-divider {
    order: 2;
    width: 100%;
    height: 1px;
    margin: clamp(0.75rem, 3vw, 1rem) 0;
    align-self: stretch;
  }

  .chat-side {
    order: 1;
    min-height: min(50dvh, 22rem);
  }
}
</style>

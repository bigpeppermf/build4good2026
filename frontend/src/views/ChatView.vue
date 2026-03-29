<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

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
  mirageSnapshot.value = sessionId ? loadWhiteboardSnapshot(sessionId) : null;
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
  const lastSessionId = getLastSessionId();
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
    const res = await fetch(apiUrl("/chat"), {
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
  currentSessionId,
  (nextSessionId, previousSessionId) => {
    if (nextSessionId !== previousSessionId) {
      messages.value = [];
      seededSessionId.value = null;
      input.value = "";
    }

    loadMirageSnapshot(nextSessionId);

    if (nextSessionId) {
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

      <p
        v-if="sessionLabel"
        class="output-session-id"
      >
        Session <span class="output-session-mono">{{ sessionLabel }}</span>
      </p>

      <div class="output-body">
        <div class="output-block">
          <p class="output-label">Analysis</p>
          <template v-if="analysisStatus === 'complete' && analysis">
            <p class="output-value">{{ analysisHeadline }}</p>
            <p class="output-line">{{ analysisEntryPointLine }}</p>
            <p class="output-line">{{ analysisMissingLine }}</p>
            <p class="output-detail">{{ analysis.summary }}</p>
          </template>
          <p v-else-if="localAnalysisDisplay" class="output-detail">
            {{ localAnalysisDisplay }}
          </p>
          <p v-else-if="analysisStatus === 'failed'" class="output-error">
            {{ analysisErrorMessage ?? "Could not load analysis output." }}
          </p>
          <p v-else-if="analysisStatus === 'processing'" class="output-placeholder">
            Processing{{ analysisStage ? ` (${analysisStage})` : "" }}...
          </p>
          <p v-else class="output-placeholder">-</p>
        </div>

        <div class="output-block">
          <p class="output-label">Feedback</p>
          <template v-if="analysisStatus === 'complete' && feedback">
            <p class="output-subheading">Strengths</p>
            <ul class="output-list">
              <li v-for="item in feedbackStrengths" :key="`strength-${item}`">{{ item }}</li>
              <li v-if="feedbackStrengths.length === 0">No strengths were listed.</li>
            </ul>

            <p class="output-subheading">Improvements</p>
            <ul class="output-list">
              <li v-for="item in feedbackImprovements" :key="`improvement-${item}`">{{ item }}</li>
              <li v-if="feedbackImprovements.length === 0">No improvements were listed.</li>
            </ul>

            <p v-if="feedbackCriticalGaps.length > 0" class="output-subheading">Critical gaps</p>
            <ul v-if="feedbackCriticalGaps.length > 0" class="output-list output-list--critical">
              <li v-for="item in feedbackCriticalGaps" :key="`gap-${item}`">{{ item }}</li>
            </ul>

            <p class="output-detail">{{ feedbackNarrative }}</p>
          </template>
          <p v-else-if="localFeedbackDisplay" class="output-detail">
            {{ localFeedbackDisplay }}
          </p>
          <p v-else-if="analysisStatus === 'failed'" class="output-error">Feedback unavailable.</p>
          <p v-else-if="analysisStatus === 'processing'" class="output-placeholder">
            Waiting for feedback...
          </p>
          <p v-else class="output-placeholder">-</p>
        </div>

        <div class="output-block">
          <p class="output-label">Score</p>
          <template v-if="analysisStatus === 'complete' && score">
            <p class="output-value">{{ score.total }} / 100 | {{ score.grade }}</p>
            <div class="score-lines">
              <p v-for="line in scoreLines" :key="line.key" class="score-line">
                <span class="score-line-label">{{ line.label }}</span>
                <span class="score-line-value">{{ line.bar }} {{ line.value }}/25</span>
              </p>
            </div>
          </template>
          <p v-else-if="localScoreDisplay" class="output-value output-value--pre">
            {{ localScoreDisplay }}
          </p>
          <p v-else-if="analysisStatus === 'failed'" class="output-error">Score unavailable.</p>
          <p v-else-if="analysisStatus === 'processing'" class="output-placeholder">
            Scoring in progress...
          </p>
          <p v-else class="output-placeholder">-</p>
        </div>

        <p class="output-note">{{ outputNote }}</p>
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

.output-session-id {
  margin: 0 0 0.5rem;
  padding: 0 0.25rem 0 0;
  font-family: var(--font-sans);
  font-size: clamp(0.6875rem, 0.65rem + 0.1vw, 0.75rem);
  color: var(--ink-muted);
  word-break: break-all;
}

.output-session-mono {
  font-family: var(--font-mono);
  font-size: 0.95em;
  color: var(--ink);
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

.output-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 0.25rem 1rem 0;
  display: flex;
  flex-direction: column;
  gap: clamp(1.25rem, 3vw, 1.75rem);
  -webkit-overflow-scrolling: touch;
}

.output-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  align-items: flex-start;
  text-align: left;
}

.output-label {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.625rem, 0.6rem + 0.15vw, 0.6875rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.output-placeholder,
.output-line {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  font-weight: 500;
  line-height: 1.5;
  color: var(--ink);
  white-space: pre-wrap;
}

.output-value--pre {
  white-space: pre-line;
}

.output-value {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  font-weight: 600;
  line-height: 1.5;
  color: var(--ink);
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

.output-subheading {
  margin: 0.25rem 0 0;
  font-family: var(--font-mono);
  font-size: clamp(0.625rem, 0.6rem + 0.15vw, 0.6875rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.output-list {
  margin: 0;
  padding-left: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
}

.output-list--critical {
  color: var(--danger);
}

.output-error {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.15vw, 0.875rem);
  color: var(--danger);
}

.score-lines {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  width: 100%;
}

.score-line {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.score-line-label {
  font-family: var(--font-mono);
  font-size: clamp(0.625rem, 0.6rem + 0.15vw, 0.6875rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.score-line-value {
  font-family: var(--font-mono);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  color: var(--ink);
  white-space: pre;
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

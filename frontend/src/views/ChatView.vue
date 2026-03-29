<script setup lang="ts">
import { ref, reactive, nextTick } from "vue";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  displayedText: string;
  streaming: boolean;
}

const messages = ref<ChatMessage[]>([]);
const input = ref("");
const isStreaming = ref(false);
const messagesEl = ref<HTMLElement | null>(null);

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
      // batch a few characters per tick for natural speed
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

function sendMessage() {
  const text = input.value.trim();
  if (!text || isStreaming.value) return;

  messages.value.push(reactive({
    role: "user",
    text,
    displayedText: text,
    streaming: false,
  }));
  input.value = "";
  scrollToBottom();

  // TODO: replace with real backend call
  isStreaming.value = true;
  setTimeout(() => {
    const response = "This is a placeholder response. Once the backend is connected, real AI responses will stream in here word by word, just like this animation shows.";
    messages.value.push(reactive({
      role: "assistant",
      text: response,
      displayedText: "",
      streaming: true,
    }));
    scrollToBottom();
    streamText(messages.value.length - 1, response);
  }, 500);
}
</script>

<template>
  <div class="chat-page">
    <section class="output-side" aria-labelledby="chat-mirage-title">
      <h2 id="chat-mirage-title" class="side-heading side-heading--mirage">
        Mirage
      </h2>

      <div class="output-body">
        <div class="output-block">
          <p class="output-label">Analysis</p>
          <p class="output-placeholder">—</p>
        </div>
        <div class="output-block">
          <p class="output-label">Feedback</p>
          <p class="output-placeholder">—</p>
        </div>
        <div class="output-block">
          <p class="output-label">Score</p>
          <p class="output-placeholder">—</p>
        </div>
        <p class="output-note">
          Output will appear here once the backend is connected.
        </p>
      </div>
    </section>

    <div class="column-divider" aria-hidden="true" />

    <section class="chat-side" aria-labelledby="chat-column-title">
      <h1 id="chat-column-title" class="side-heading side-heading--chat">
        Chat
      </h1>

      <div ref="messagesEl" class="chat-messages">
        <p v-if="messages.length === 0" class="chat-empty">
          No messages yet. Start a conversation.
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
          placeholder="Message…"
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
  /* Bleed into `<main>` padding so the two columns use the full content area */
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

/* Same shimmer motion as `.hero-brand` on HomeView, at column title size */
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

/* ── Chat column ── */

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
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.3); }
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
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
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
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
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

/* ── Output column ── */

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

.output-placeholder {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  font-weight: 500;
  line-height: 1.5;
  color: var(--ink-faint);
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
}

@media (max-width: 768px) {
  .chat-page {
    flex-direction: column;
    min-height: calc(100dvh - 2 * var(--page-pad-y, 1.25rem));
  }

  /* Keep chat above the fold on small screens (DOM order is AI | chat) */
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

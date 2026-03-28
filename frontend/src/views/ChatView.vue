<script setup lang="ts">
import { ref } from "vue";

const messages = ref<{ role: "user" | "assistant"; text: string }[]>([]);
const input = ref("");

function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  messages.value.push({ role: "user", text });
  input.value = "";
  // TODO: wire to backend API and push assistant response
}
</script>

<template>
  <div class="chat-page">
    <div class="output-side">
      <h2 class="panel-title">AI Output</h2>

      <div class="output-window">
        <div class="output-body">
          <div class="output-placeholder">
            <p class="output-label">Analysis</p>
            <div class="output-slot" />
          </div>
          <div class="output-placeholder">
            <p class="output-label">Feedback</p>
            <div class="output-slot" />
          </div>
          <div class="output-placeholder">
            <p class="output-label">Score</p>
            <div class="output-slot output-slot--small" />
          </div>
        </div>
        <p class="output-note">
          Output will appear here once the backend is connected.
        </p>
      </div>
    </div>

    <div class="chat-side">
      <h1 class="panel-title">Chat</h1>

      <div class="chat-window">
        <div class="chat-messages">
          <p v-if="messages.length === 0" class="chat-empty">
            No messages yet. Start a conversation.
          </p>
          <div
            v-for="(msg, i) in messages"
            :key="i"
            class="chat-bubble"
            :class="msg.role"
          >
            <span class="chat-role">{{ msg.role === "user" ? "You" : "AI" }}</span>
            <p class="chat-text">{{ msg.text }}</p>
          </div>
        </div>

        <form class="chat-input-bar" @submit.prevent="sendMessage">
          <input
            v-model="input"
            class="chat-input"
            type="text"
            placeholder="Type a message…"
          />
          <button type="submit" class="btn-send" :disabled="!input.trim()">
            Send
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  width: 100%;
  height: calc(100vh - var(--page-pad-y, 2rem) * 2);
  display: flex;
  gap: clamp(0.75rem, 2vw, 1.25rem);
  padding: clamp(1.5rem, 4vw, 2.75rem) clamp(1rem, 3vw, 2rem);
}

.chat-side,
.output-side {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.panel-title {
  margin: 0 0 clamp(0.75rem, 2vw, 1rem);
  font-family: var(--font-display);
  font-size: clamp(1.25rem, 3vw + 0.25rem, 1.65rem);
  font-weight: 700;
  color: var(--ink);
  letter-spacing: -0.03em;
  line-height: 1.1;
}

/* ── Chat panel ── */

.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  background: var(--bg-elevated);
  box-shadow:
    0 1px 0 rgb(255 255 255 / 0.05) inset,
    0 24px 48px -32px rgb(0 0 0 / 0.5);
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: clamp(1rem, 3vw, 1.5rem);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.chat-empty {
  margin: auto;
  font-size: clamp(0.8125rem, 0.8rem + 0.2vw, 0.9375rem);
  color: var(--ink-muted);
}

.chat-bubble {
  max-width: 75%;
  padding: 0.65rem 0.85rem;
  border-radius: 4px;
  border: 1px solid var(--line);
}

.chat-bubble.user {
  align-self: flex-end;
  background: rgb(255 255 255 / 0.06);
}

.chat-bubble.assistant {
  align-self: flex-start;
  background: var(--bg-soft, rgb(255 255 255 / 0.03));
}

.chat-role {
  display: block;
  margin-bottom: 0.25rem;
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.1vw, 0.625rem);
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.chat-text {
  margin: 0;
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  line-height: 1.55;
  color: var(--ink);
}

.chat-input-bar {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem clamp(1rem, 3vw, 1.5rem);
  border-top: 1px solid var(--line);
  background: rgb(0 0 0 / 0.15);
}

.chat-input {
  flex: 1;
  min-height: 2.75rem;
  padding: 0.55rem 0.75rem;
  font-family: var(--font-sans);
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  color: var(--ink);
  background: rgb(255 255 255 / 0.04);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  outline: none;
  transition: border-color 0.15s ease;
}

.chat-input:focus {
  border-color: var(--accent);
}

.btn-send {
  min-height: 2.75rem;
  padding: 0.55rem 1.15rem;
  font-family: var(--font-sans);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--void);
  background: var(--ink);
  border: 1px solid rgb(255 255 255 / 0.12);
  border-radius: 4px;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}

.btn-send:hover:not(:disabled) {
  background: #f2f5f1;
  border-color: rgb(255 255 255 / 0.2);
}

.btn-send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-send:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

/* ── Output panel ── */

.output-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  background: var(--bg-elevated);
  box-shadow:
    0 1px 0 rgb(255 255 255 / 0.05) inset,
    0 24px 48px -32px rgb(0 0 0 / 0.5);
  overflow: hidden;
}

.output-body {
  flex: 1;
  overflow-y: auto;
  padding: clamp(1rem, 3vw, 1.5rem);
  display: flex;
  flex-direction: column;
  gap: clamp(1rem, 3vw, 1.25rem);
}

.output-placeholder {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.output-label {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.625rem, 0.6rem + 0.15vw, 0.6875rem);
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.output-slot {
  min-height: 6rem;
  border-radius: 3px;
  border: 1px dashed var(--line-strong);
  background: rgb(0 0 0 / 0.15);
}

.output-slot--small {
  min-height: 3rem;
}

.output-note {
  margin: 0;
  padding: 0.75rem clamp(1rem, 3vw, 1.5rem);
  border-top: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.1vw, 0.625rem);
  letter-spacing: 0.08em;
  color: var(--ink-faint);
  text-align: center;
  background: rgb(0 0 0 / 0.15);
}

/* ── Responsive ── */

@media (max-width: 768px) {
  .chat-page {
    flex-direction: column;
    height: auto;
    min-height: calc(100vh - var(--page-pad-y, 2rem) * 2);
  }

  .chat-side,
  .output-side {
    min-height: 20rem;
  }
}
</style>

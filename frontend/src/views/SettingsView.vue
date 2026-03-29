<script setup lang="ts">
import { ref } from "vue";

const emailNotifications = ref(true);
const sessionReminders = ref(false);
const analyticsOptIn = ref(true);
</script>

<template>
  <div class="settings-page">
    <header class="settings-header">
      <h1 class="settings-title">
        Settings
      </h1>
      <p class="settings-lead">
        Manage preferences for Mirage. More options will appear as features ship.
      </p>
    </header>

    <div class="settings-sections">
      <section
        class="settings-section"
        aria-labelledby="settings-general"
      >
        <h2
          id="settings-general"
          class="settings-section-title"
        >
          General
        </h2>
        <ul class="settings-list">
          <li class="settings-row">
            <div class="settings-row-text">
              <span class="settings-label">Language</span>
              <span class="settings-hint">Interface language</span>
            </div>
            <select
              class="settings-select"
              aria-label="Language"
            >
              <option>English</option>
            </select>
          </li>
          <li class="settings-row">
            <div class="settings-row-text">
              <span class="settings-label">Time zone</span>
              <span class="settings-hint">Used for session timestamps</span>
            </div>
            <select
              class="settings-select"
              aria-label="Time zone"
            >
              <option>Local (browser)</option>
            </select>
          </li>
        </ul>
      </section>

      <section
        class="settings-section"
        aria-labelledby="settings-notifications"
      >
        <h2
          id="settings-notifications"
          class="settings-section-title"
        >
          Notifications
        </h2>
        <ul class="settings-list">
          <li class="settings-row settings-row--toggle">
            <div class="settings-row-text">
              <span class="settings-label">Email updates</span>
              <span class="settings-hint">Product news and tips</span>
            </div>
            <label class="settings-switch">
              <input
                v-model="emailNotifications"
                type="checkbox"
                class="settings-checkbox"
              >
              <span class="settings-switch-ui" />
            </label>
          </li>
          <li class="settings-row settings-row--toggle">
            <div class="settings-row-text">
              <span class="settings-label">Session reminders</span>
              <span class="settings-hint">Nudge before a scheduled practice</span>
            </div>
            <label class="settings-switch">
              <input
                v-model="sessionReminders"
                type="checkbox"
                class="settings-checkbox"
              >
              <span class="settings-switch-ui" />
            </label>
          </li>
        </ul>
      </section>

      <section
        class="settings-section"
        aria-labelledby="settings-privacy"
      >
        <h2
          id="settings-privacy"
          class="settings-section-title"
        >
          Privacy
        </h2>
        <ul class="settings-list">
          <li class="settings-row settings-row--toggle">
            <div class="settings-row-text">
              <span class="settings-label">Usage analytics</span>
              <span class="settings-hint">Help improve Mirage with anonymous usage</span>
            </div>
            <label class="settings-switch">
              <input
                v-model="analyticsOptIn"
                type="checkbox"
                class="settings-checkbox"
              >
              <span class="settings-switch-ui" />
            </label>
          </li>
        </ul>
      </section>

      <p class="settings-note">
        Account authentication is now active. These preference toggles are still local-only until settings sync is wired to the backend.
      </p>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  width: 100%;
  max-width: min(42rem, 100%);
  margin: 0 auto;
  padding: clamp(1rem, 3vw, 1.5rem) 0 clamp(2rem, 5vw, 3rem);
}

.settings-header {
  margin-bottom: clamp(1.5rem, 4vw, 2rem);
}

.settings-title {
  margin: 0 0 0.5rem;
  font-family: var(--font-display);
  font-size: clamp(1.65rem, 4vw + 0.5rem, 2.35rem);
  font-weight: 700;
  color: var(--pop);
  letter-spacing: -0.03em;
  line-height: 1.1;
  text-align: left;
}

.settings-lead {
  margin: 0;
  font-size: clamp(0.9375rem, 0.9rem + 0.2vw, 1.0625rem);
  line-height: 1.55;
  color: var(--ink-muted);
}

.settings-sections {
  display: flex;
  flex-direction: column;
  gap: clamp(1.5rem, 4vw, 2rem);
}

.settings-section {
  margin: 0;
  padding: clamp(1rem, 2.5vw, 1.25rem) clamp(1rem, 2.5vw, 1.35rem);
  border: 1px dashed rgb(224 112 86 / 0.45);
  border-radius: 4px;
  background: rgb(224 112 86 / 0.05);
}

.settings-section-title {
  margin: 0 0 1rem;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.15vw, 0.75rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgb(224 112 86 / 0.95);
}

.settings-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.settings-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1rem;
  padding: 0.85rem 0;
  border-top: 1px solid var(--line);
}

.settings-row:first-of-type {
  border-top: none;
  padding-top: 0;
}

.settings-row:last-child {
  padding-bottom: 0;
}

.settings-row-text {
  flex: 1;
  min-width: min(100%, 12rem);
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  text-align: left;
}

.settings-label {
  font-family: var(--font-sans);
  font-size: clamp(0.875rem, 0.85rem + 0.15vw, 0.9375rem);
  font-weight: 600;
  color: var(--ink);
}

.settings-hint {
  font-size: clamp(0.75rem, 0.72rem + 0.1vw, 0.8125rem);
  color: var(--ink-muted);
  line-height: 1.4;
}

.settings-select {
  min-width: 10rem;
  max-width: 100%;
  padding: 0.45rem 0.65rem;
  font-family: var(--font-mono);
  font-size: clamp(0.8125rem, 0.8rem + 0.1vw, 0.875rem);
  font-weight: 500;
  color: var(--ink);
  background: var(--surface-faint);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  outline: none;
  cursor: pointer;
}

.settings-select:focus {
  border-color: var(--accent);
}

.settings-row--toggle {
  align-items: center;
}

.settings-switch {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  cursor: pointer;
}

.settings-checkbox {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.settings-switch-ui {
  position: relative;
  display: block;
  width: 2.5rem;
  height: 1.35rem;
  border-radius: 999px;
  background: rgb(0 0 0 / 0.35);
  border: 1px solid var(--line);
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}

.settings-switch-ui::after {
  content: "";
  position: absolute;
  top: 2px;
  left: 2px;
  width: calc(1.35rem - 4px);
  height: calc(1.35rem - 4px);
  border-radius: 50%;
  background: var(--ink);
  transition: transform 0.2s ease;
}

.settings-checkbox:checked + .settings-switch-ui {
  background: rgb(224 112 86 / 0.35);
  border-color: rgb(224 112 86 / 0.55);
}

.settings-checkbox:checked + .settings-switch-ui::after {
  transform: translateX(1.1rem);
  background: var(--pop);
}

.settings-checkbox:focus-visible + .settings-switch-ui {
  outline: 2px solid var(--focus);
  outline-offset: 3px;
}

.settings-note {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.1vw, 0.625rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.06em;
  color: var(--ink-faint);
  line-height: 1.5;
}
</style>

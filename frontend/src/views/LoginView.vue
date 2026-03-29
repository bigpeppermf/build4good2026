<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <p class="login-meta">
        Sign in
      </p>
      <h1 class="login-title">
        Welcome back
      </h1>
      <p class="login-lead">
        Account sign-in is not configured in this build. Use the app from the sidebar: Dashboard for capture, Chat for snapshots and agent messages.
      </p>
      <div class="login-actions">
        <RouterLink
          :to="{ name: 'dashboard' }"
          class="btn-dashboard"
        >
          Go to Dashboard
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  width: 100%;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(1.5rem, 4vw, 3rem);
}

.login-card {
  width: 100%;
  max-width: min(26rem, 100%);
  padding: clamp(1.35rem, 4.5vw, 2.25rem) clamp(1rem, 3.5vw, 1.75rem);
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  background: var(--bg-elevated);
  box-shadow:
    0 1px 0 var(--edge-inset) inset,
    0 32px 64px -36px rgb(0 0 0 / 0.65);
  text-align: center;
}

.login-meta {
  margin: 0 0 clamp(0.75rem, 2vw, 1rem);
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.2vw, 0.6875rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.login-title {
  margin: 0 0 0.5rem;
  font-family: var(--font-display);
  font-size: clamp(1.65rem, 4vw + 0.5rem, 2.35rem);
  font-weight: 700;
  color: var(--ink);
  letter-spacing: -0.03em;
  line-height: 1.1;
}

.login-lead {
  margin: 0 0 clamp(1.25rem, 3vw, 1.75rem);
  font-size: clamp(0.9375rem, 0.9rem + 0.25vw, 1.0625rem);
  line-height: 1.6;
  color: var(--ink-muted);
  text-wrap: pretty;
}

.login-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.btn-dashboard {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  padding: 0.55rem 1.35rem;
  font-family: var(--font-sans);
  font-size: clamp(0.8125rem, 0.8rem + 0.15vw, 0.875rem);
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--void);
  background: var(--ink);
  border: 1px solid var(--btn-ink-border);
  border-radius: 4px;
  text-decoration: none;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}

.btn-dashboard:hover {
  background: var(--btn-ink-bg-hover);
  border-color: var(--btn-ink-border-hover);
}

.btn-dashboard:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

@media (max-width: 480px) {
  .login-card {
    padding: 1.25rem 1rem;
  }
}
</style>

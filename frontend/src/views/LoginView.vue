<script setup lang="ts">
// Clerk auth will be wired here — this is a placeholder
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
        Sign in to access your practice sessions and feedback.
      </p>

      <!-- Clerk auth component will replace this block -->
      <div class="login-placeholder">
        <div class="field">
          <label class="field-label" for="email">Email</label>
          <input
            id="email"
            class="field-input"
            type="email"
            placeholder="you@example.com"
            disabled
          />
        </div>
        <div class="field">
          <label class="field-label" for="password">Password</label>
          <input
            id="password"
            class="field-input"
            type="password"
            placeholder="********"
            disabled
          />
        </div>
        <button
          type="button"
          class="btn-login"
          disabled
        >
          Sign in
        </button>
        <p class="login-note">
          Clerk auth placeholder — inputs are disabled until integration.
        </p>
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
    0 1px 0 rgb(255 255 255 / 0.06) inset,
    0 32px 64px -36px rgb(0 0 0 / 0.65);
  text-align: center;
}

.login-meta {
  margin: 0 0 clamp(0.75rem, 2vw, 1rem);
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.2vw, 0.6875rem);
  font-weight: 500;
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
}

.login-placeholder {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  text-align: left;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field-label {
  font-family: var(--font-mono);
  font-size: clamp(0.625rem, 0.6rem + 0.15vw, 0.6875rem);
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.field-input {
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

.field-input:focus {
  border-color: var(--accent);
}

.field-input:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-login {
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

.btn-login:hover:not(:disabled) {
  background: #f2f5f1;
  border-color: rgb(255 255 255 / 0.2);
}

.btn-login:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-login:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

.login-note {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.1vw, 0.625rem);
  letter-spacing: 0.08em;
  color: var(--ink-faint);
  text-align: center;
}

@media (max-width: 480px) {
  .login-card {
    padding: 1.25rem 1rem;
  }
}
</style>

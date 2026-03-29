<script setup lang="ts">
import { ClerkLoaded, ClerkLoading, Show, SignIn } from "@clerk/vue";
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();

const redirectUrl = computed(() => {
  const candidate = route.query.redirect;
  if (typeof candidate === "string" && candidate.startsWith("/")) {
    return candidate;
  }
  return "/dashboard";
});
</script>

<template>
  <div class="login-page">
    <ClerkLoading>
      <div class="login-card login-card--status">
        <p class="login-meta">
          Sign in
        </p>
        <p class="login-status">
          Loading authentication…
        </p>
      </div>
    </ClerkLoading>

    <ClerkLoaded>
      <Show when="signed-out">
        <div class="login-card">
          <p class="login-meta">
            Sign in
          </p>
          <h1 class="login-title">
            Keep each practice run tied to one account
          </h1>
          <p class="login-lead">
            Mirage now scopes sessions, analysis, and local browser snapshots to the authenticated user. Sign in to start a secure session.
          </p>
          <div class="login-auth">
            <SignIn
              :force-redirect-url="redirectUrl"
              :fallback-redirect-url="redirectUrl"
            />
          </div>
        </div>
      </Show>

      <Show when="signed-in">
        <div class="login-card login-card--status">
          <p class="login-meta">
            Sign in
          </p>
          <p class="login-status">
            Redirecting to your workspace…
          </p>
        </div>
      </Show>
    </ClerkLoaded>
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
  max-width: min(32rem, 100%);
  padding: clamp(1.35rem, 4.5vw, 2.25rem) clamp(1rem, 3.5vw, 1.75rem);
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  background: var(--bg-elevated);
  box-shadow:
    0 1px 0 var(--edge-inset) inset,
    0 32px 64px -36px rgb(0 0 0 / 0.65);
}

.login-card--status {
  max-width: min(24rem, 100%);
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

.login-lead,
.login-status {
  margin: 0;
  font-size: clamp(0.9375rem, 0.9rem + 0.25vw, 1.0625rem);
  line-height: 1.6;
  color: var(--ink-muted);
  text-wrap: pretty;
}

.login-auth {
  margin-top: clamp(1.25rem, 3vw, 1.75rem);
  display: flex;
  justify-content: center;
}

@media (max-width: 480px) {
  .login-card {
    padding: 1.25rem 1rem;
  }
}
</style>

<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router";

const route = useRoute();
</script>

<template>
  <header
    class="nav-float"
    aria-label="Site"
  >
    <div class="nav-card">
      <p
        class="nav-meta"
        aria-hidden="true"
      >
        Index
      </p>
      <RouterLink
        to="/"
        class="nav-brand"
        :aria-current="route.name === 'home' ? 'page' : undefined"
      >
        Home
      </RouterLink>
      <nav
        class="nav-actions"
        aria-label="Main"
      >
        <RouterLink
          :to="{ name: 'dashboard' }"
          class="btn-dashboard"
          :aria-current="route.name === 'dashboard' ? 'page' : undefined"
        >
          Dashboard
        </RouterLink>
      </nav>
    </div>
  </header>
</template>

<style scoped>
.nav-float {
  position: fixed;
  top: max(0.75rem, env(safe-area-inset-top, 0px));
  right: max(0.75rem, env(safe-area-inset-right, 0px));
  z-index: 50;
  pointer-events: none;
}

.nav-card {
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.4rem;
  min-width: min(10rem, calc(100vw - 1.5rem - env(safe-area-inset-right, 0px)));
  max-width: calc(100vw - 1.5rem - env(safe-area-inset-left, 0px) - env(safe-area-inset-right, 0px));
  padding: 0.5rem 0.6rem 0.6rem;
  background: var(--bg-elevated);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  box-shadow:
    0 24px 56px -28px rgb(0 0 0 / 0.55),
    0 0 0 1px rgb(255 255 255 / 0.05) inset;
}

.nav-meta {
  margin: 0;
  padding: 0 0.35rem 0.4rem;
  font-family: var(--font-mono);
  font-size: 0.5625rem;
  font-weight: 500;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-faint);
  border-bottom: 1px solid var(--line);
}

.nav-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  padding: 0.35rem 0.5rem;
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink);
  text-decoration: none;
  text-align: center;
  border-radius: 3px;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.nav-brand:hover {
  background: var(--accent-soft);
  color: var(--accent-hover);
}

.nav-brand[aria-current="page"] {
  background: rgb(255 255 255 / 0.06);
  color: var(--accent-hover);
}

.nav-brand:focus-visible,
.btn-dashboard:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

.nav-actions {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.btn-dashboard {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  padding: 0.45rem 0.65rem;
  font-family: var(--font-display);
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-decoration: none;
  text-align: center;
  color: var(--void);
  background: var(--ink);
  border: 1px solid rgb(255 255 255 / 0.1);
  border-radius: 4px;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    transform 0.15s ease,
    color 0.15s ease;
}

.btn-dashboard:hover {
  background: #f2f5f1;
  border-color: rgb(255 255 255 / 0.18);
  transform: translateY(-1px);
}

.btn-dashboard[aria-current="page"] {
  background: var(--pop);
  border-color: var(--pop);
  color: var(--void);
}

@media (max-width: 480px) {
  .nav-float {
    top: max(0.5rem, env(safe-area-inset-top, 0px));
    right: max(0.5rem, env(safe-area-inset-right, 0px));
  }

  .nav-card {
    min-width: min(9rem, calc(100vw - 1.25rem));
    padding: 0.45rem 0.5rem 0.55rem;
  }

  .nav-brand,
  .btn-dashboard {
    min-height: 2.625rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn-dashboard:hover {
    transform: none;
  }
}
</style>

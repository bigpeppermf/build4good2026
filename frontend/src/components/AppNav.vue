<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router";

const route = useRoute();
</script>

<template>
  <aside
    class="sidebar"
    aria-label="Site"
  >
    <div class="sidebar-user">
      <div class="user-avatar" aria-hidden="true" />
      <span class="user-name">User</span>
    </div>

    <nav class="sidebar-nav" aria-label="Main">
      <RouterLink
        to="/"
        class="nav-link"
        :aria-current="route.name === 'home' ? 'page' : undefined"
      >
        Home
      </RouterLink>
      <RouterLink
        :to="{ name: 'dashboard' }"
        class="nav-link"
        :aria-current="route.name === 'dashboard' ? 'page' : undefined"
      >
        Dashboard
      </RouterLink>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 50;
  width: var(--sidebar-width, 13rem);
  display: flex;
  flex-direction: column;
  padding: clamp(1rem, 3vw, 1.5rem) 0.75rem;
  background: var(--bg-elevated);
  border-right: 1px solid var(--rose-line);
  box-shadow:
    1px 0 0 rgb(255 255 255 / 0.05) inset,
    4px 0 24px -8px rgb(0 0 0 / 0.35);
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.5rem 1rem;
  margin-bottom: 0.75rem;
  border-bottom: 1px solid var(--line);
}

.user-avatar {
  flex-shrink: 0;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: var(--line-strong, rgb(255 255 255 / 0.12));
}

.user-name {
  font-family: var(--font-sans);
  font-size: clamp(0.8125rem, 0.8rem + 0.15vw, 0.875rem);
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.nav-link {
  display: flex;
  align-items: center;
  min-height: 2.5rem;
  padding: 0.4rem 0.65rem;
  font-family: var(--font-mono);
  font-size: clamp(0.6875rem, 0.65rem + 0.15vw, 0.75rem);
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-muted);
  text-decoration: none;
  border-radius: 4px;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.nav-link:hover {
  background: var(--accent-soft);
  color: var(--accent-hover);
}

.nav-link[aria-current="page"] {
  background: rgb(255 255 255 / 0.06);
  color: var(--ink);
  font-weight: 600;
}

.nav-link:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}

@media (max-width: 480px) {
  .sidebar {
    width: var(--sidebar-width, 10rem);
    padding: 0.75rem 0.5rem;
  }

  .sidebar-user {
    padding: 0.4rem 0.4rem 0.75rem;
  }

  .user-avatar {
    width: 1.75rem;
    height: 1.75rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .nav-link:hover {
    transition: none;
  }
}
</style>

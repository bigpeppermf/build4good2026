<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router";

const route = useRoute();
</script>

<template>
  <aside
    class="sidebar"
    aria-label="Site"
  >
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
      <RouterLink
        :to="{ name: 'settings' }"
        class="nav-link"
        :aria-current="route.name === 'settings' ? 'page' : undefined"
      >
        Settings
      </RouterLink>

      <RouterLink
        :to="{ name: 'chat' }"
        class="nav-link"
        :aria-current="route.name === 'chat' ? 'page' : undefined"
      >
        Chat
      </RouterLink>
    </nav>

    <div class="sidebar-user">
      <div class="user-avatar" aria-hidden="true" />
      <span class="user-name">User</span>
    </div>
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
  border-right: 1px solid rgb(224 112 86 / 0.22);
  box-shadow:
    1px 0 0 rgb(224 112 86 / 0.08) inset,
    4px 0 24px -8px rgb(0 0 0 / 0.35);
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-top: auto;
  padding: 1rem 0.5rem 0.5rem;
  border-top: 1px solid rgb(224 112 86 / 0.2);
}

.user-avatar {
  flex-shrink: 0;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: rgb(224 112 86 / 0.25);
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
  font-weight: var(--font-mono-weight);
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
  background: rgb(224 112 86 / 0.12);
  color: var(--pop);
}

.nav-link[aria-current="page"] {
  background: rgb(224 112 86 / 0.14);
  color: var(--pop);
  font-weight: var(--font-mono-weight);
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
    padding: 0.75rem 0.4rem 0.4rem;
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

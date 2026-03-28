<script setup lang="ts">
import { RouterView } from "vue-router";
import AppNav from "./components/AppNav.vue";
</script>

<template>
  <div class="shell">
    <AppNav />
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  color: var(--ink);
}

.main {
  flex: 1;
  width: 100%;
  max-width: 100%;
  padding-left: var(--page-pad-x);
  padding-right: var(--nav-clearance);
  padding-top: max(var(--page-pad-y), env(safe-area-inset-top, 0px));
  padding-bottom: max(var(--page-pad-y), env(safe-area-inset-bottom, 0px));
}

@media (min-width: 900px) {
  .main {
    padding-right: max(var(--page-pad-x), calc(env(safe-area-inset-right, 0px) + 7.25rem));
  }
}

@media (max-width: 380px) {
  .main {
    padding-left: max(0.75rem, env(safe-area-inset-left, 0px));
    padding-right: max(0.75rem, calc(env(safe-area-inset-right, 0px) + 5.25rem));
  }
}
</style>

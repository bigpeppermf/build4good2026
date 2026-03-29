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
  flex-direction: row;
  color: var(--ink);
}

.main {
  flex: 1;
  min-width: 0;
  overflow-x: clip;
  margin-left: var(--sidebar-width, 13rem);
  padding-left: var(--page-pad-x);
  padding-right: var(--page-pad-x);
  padding-top: max(var(--page-pad-y), env(safe-area-inset-top, 0px));
  padding-bottom: max(var(--page-pad-y), env(safe-area-inset-bottom, 0px));
}

@media (max-width: 480px) {
  .main {
    margin-left: var(--sidebar-width, 10rem);
    padding-left: max(0.75rem, env(safe-area-inset-left, 0px));
    padding-right: max(0.75rem, env(safe-area-inset-right, 0px));
  }
}
</style>

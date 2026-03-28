<script setup lang="ts">
import { onMounted, ref } from "vue";

type Health = { ok: boolean };

const health = ref<Health | null>(null);

onMounted(async () => {
  try {
    const r = await fetch("/api/health");
    health.value = (await r.json()) as Health;
  } catch {
    health.value = { ok: false };
  }
});
</script>

<template>
  <main class="app">
    <p class="muted">
      API:
      <template v-if="health === null">
        …
      </template>
      <template v-else-if="health.ok">
        reachable
      </template>
      <template v-else>
        not reachable (is the backend running?)
      </template>
    </p>
  </main>
</template>

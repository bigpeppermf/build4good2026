<script setup lang="ts">
import { ClerkLoaded, ClerkLoading, useAuth } from "@clerk/vue";
import { computed, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import AppNav from "./components/AppNav.vue";

const route = useRoute();
const router = useRouter();
const { isLoaded, isSignedIn } = useAuth();

const isProtectedRoute = computed(() => route.meta.requiresAuth === true);

function sanitizeRedirect(target: unknown): string | null {
  if (typeof target !== "string" || !target.startsWith("/")) {
    return null;
  }
  return target;
}

watch(
  [() => route.fullPath, isLoaded, isSignedIn],
  ([nextPath, nextIsLoaded, nextIsSignedIn]) => {
    if (!nextIsLoaded) {
      return;
    }

    if (!nextIsSignedIn && isProtectedRoute.value) {
      void router.replace({
        name: "login",
        query: { redirect: nextPath },
      });
      return;
    }

    if (nextIsSignedIn && route.name === "login") {
      const redirectTarget = sanitizeRedirect(route.query.redirect) ?? "/dashboard";
      if (redirectTarget !== route.fullPath) {
        void router.replace(redirectTarget);
      }
    }
  },
  { immediate: true },
);
</script>

<template>
  <ClerkLoading>
    <div class="loading-shell">
      <p class="loading-copy">
        Loading authentication…
      </p>
    </div>
  </ClerkLoading>

  <ClerkLoaded>
    <div class="shell">
      <AppNav />
      <main class="main">
        <RouterView />
      </main>
    </div>
  </ClerkLoaded>
</template>

<style scoped>
.loading-shell {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
}

.loading-copy {
  margin: 0;
  font-family: var(--font-mono);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: var(--font-mono-weight);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

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

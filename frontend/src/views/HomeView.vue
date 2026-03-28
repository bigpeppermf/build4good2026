<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <section
    class="hero"
    aria-labelledby="hero-title"
  >
    <div
      class="hero-watermark"
      aria-hidden="true"
    >
      <span class="wm">Practice</span>
      <span class="wm">Practice</span>
      <span class="wm">Practice</span>
      <span class="wm">Practice</span>
    </div>

    <div class="hero-frame">
      <p class="hero-meta">
        <span class="meta-label">Whiteboard interview practice</span>
        <span
          class="meta-sep"
          aria-hidden="true"
        >·</span>
        <span class="meta-ref">Ref. UI-001</span>
      </p>

      <h1
        id="hero-title"
        class="hero-title"
      >
        <span class="title-line">Think on the board.</span>
        <span class="title-line">Explain as you draw.</span>
        <span class="title-line title-accent">Build the habit.</span>
      </h1>

      <p class="hero-lead">
        A calm place to rehearse how you communicate under pressure—voice,
        markers, and motion—without shipping full video to the server.
      </p>

      <div class="hero-cta">
        <RouterLink
          :to="{ name: 'dashboard' }"
          class="cta-mojo"
          aria-label="Start session"
        >
          <span
            class="mojo-inner"
            aria-hidden="true"
          >Start · Start · Start</span>
        </RouterLink>
      </div>

      <RouterLink
        :to="{ name: 'dashboard' }"
        class="cta-ghost"
      >
        Begin capture
      </RouterLink>
    </div>

    <p
      class="scroll-hint"
      aria-hidden="true"
    >
      <span class="scroll-line" />
      <span class="scroll-text">Scroll</span>
    </p>
  </section>
</template>

<style scoped>
.hero {
  position: relative;
  overflow: hidden;
  width: 100%;
  max-width: 100%;
  min-height: min(100dvh, 56rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: clamp(3.5rem, 10vw, 6.5rem) 0 clamp(4.5rem, 12vw, 6rem);
}

.hero-watermark {
  position: absolute;
  inset: -8% -20%;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-content: center;
  gap: 0.12em 0.4em;
  pointer-events: none;
  transform: rotate(-7deg);
  font-family: var(--font-display);
  font-size: clamp(2.75rem, 12vw + 1rem, 8.5rem);
  font-weight: 800;
  line-height: 0.85;
  letter-spacing: -0.04em;
  color: var(--ink);
  opacity: 0.04;
  user-select: none;
}

.wm {
  white-space: nowrap;
}

.hero-frame {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: min(40rem, 100%);
  text-align: center;
  padding: clamp(1.35rem, 4.5vw, 2.6rem) clamp(1rem, 3.5vw, 1.75rem);
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  background: var(--bg-elevated);
  box-shadow:
    0 1px 0 rgb(255 255 255 / 0.06) inset,
    0 32px 64px -36px rgb(0 0 0 / 0.65);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.hero-meta {
  margin: 0 0 clamp(1rem, 3vw, 1.5rem);
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.2vw, 0.6875rem);
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.meta-sep {
  margin: 0 0.45rem;
  color: var(--line-strong);
}

.hero-title {
  margin: 0 0 clamp(1rem, 2.5vw, 1.35rem);
  font-family: var(--font-display);
  font-size: clamp(2rem, 6.5vw + 0.5rem, 3.85rem);
  font-weight: 700;
  line-height: 1.03;
  letter-spacing: -0.03em;
  color: var(--ink);
  text-wrap: balance;
}

.title-line {
  display: block;
}

.title-accent {
  font-family: var(--font-serif);
  font-style: italic;
  font-weight: 500;
  font-size: 0.92em;
  color: var(--accent-hover);
}

.hero-lead {
  margin: 0 auto clamp(1.35rem, 4vw, 1.85rem);
  max-width: 34rem;
  font-size: clamp(0.9375rem, 0.9rem + 0.35vw, 1.0625rem);
  font-weight: 400;
  line-height: 1.68;
  color: var(--ink-muted);
  text-wrap: pretty;
}

.hero-cta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  justify-content: center;
  align-items: stretch;
  margin-bottom: 0.65rem;
}

.cta-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  padding: 0.65rem 1.5rem;
  font-family: var(--font-sans);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  text-decoration: none;
  color: var(--void);
  background: var(--ink);
  border: 1px solid rgb(255 255 255 / 0.12);
  border-radius: 4px;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    transform 0.2s ease,
    color 0.2s ease;
}

.cta-primary:hover {
  background: #f2f5f1;
  border-color: rgb(255 255 255 / 0.2);
  transform: translateY(-1px);
}

.cta-primary:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 3px;
}

.cta-mojo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  padding: 0.65rem 1rem;
  font-family: var(--font-display);
  font-size: clamp(0.75rem, 0.72rem + 0.15vw, 0.8125rem);
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  text-decoration: none;
  color: var(--ink);
  background: rgb(255 255 255 / 0.04);
  border: 1px dashed var(--line-strong);
  border-radius: 4px;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.cta-mojo:hover {
  border-color: var(--pop);
  color: var(--pop);
  background: rgb(224 112 86 / 0.1);
}

.cta-mojo:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 3px;
}

.mojo-inner {
  letter-spacing: 0.04em;
}

.cta-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  padding: 0.5rem 1rem;
  font-family: var(--font-mono);
  font-size: clamp(0.5625rem, 0.55rem + 0.15vw, 0.625rem);
  font-weight: 500;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  text-decoration: none;
  color: var(--ink-muted);
  border: none;
  border-radius: 0;
  background: transparent;
  transition: color 0.2s ease;
}

.cta-ghost:hover {
  color: var(--ink);
}

.cta-ghost:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 3px;
  border-radius: 2px;
}

.scroll-hint {
  position: absolute;
  bottom: max(1.25rem, env(safe-area-inset-bottom, 0px));
  left: 50%;
  transform: translateX(-50%);
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.625rem;
  font-weight: 500;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--ink-faint);
}

.scroll-line {
  display: block;
  width: 1px;
  height: clamp(1.5rem, 4vw, 2rem);
  background-color: var(--line-strong);
  opacity: 0.65;
}

.scroll-text {
  margin-top: 0.15rem;
}

@media (max-width: 640px) {
  .hero {
    min-height: min(100dvh, 52rem);
    padding-top: clamp(3rem, 8vw, 4rem);
  }

  .hero-meta {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    letter-spacing: 0.1em;
  }

  .meta-sep {
    display: none;
  }

  .hero-cta {
    flex-direction: column;
    width: 100%;
  }

  .cta-primary,
  .cta-mojo {
    width: 100%;
  }
}

@media (min-width: 641px) and (max-width: 899px) {
  .hero-cta {
    justify-content: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cta-primary:hover {
    transform: none;
  }
}
</style>

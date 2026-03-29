<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <section
    class="hero"
    aria-labelledby="hero-brand"
  >
    <div
      class="hero-watermark"
      aria-hidden="true"
    >
      <div class="wm-row wm-scroll-left"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-right"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-left"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-right"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-left"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-right"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-left"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-right"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-left"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
      <div class="wm-row wm-scroll-right"><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span><span class="wm-track">Practice Practice Practice Practice Practice Practice Practice Practice Practice Practice&nbsp;</span></div>
    </div>

    <div class="hero-content">
      <h2
        id="hero-brand"
        class="hero-brand"
      >
        Mirage
      </h2>

      <div class="hero-frame">
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
    </div>

  </section>
</template>

<style scoped>
.hero {
  position: relative;
  /* Single page scroll: clip spill from watermark / brand so the viewport doesn’t get a second bar */
  overflow: clip;
  width: 100%;
  max-width: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  box-sizing: border-box;
  /* ~half the upper “air” vs centered: start lower on the screen */
  padding: clamp(5rem, 22vh, 16rem) clamp(1rem, 3vw, 2rem) clamp(2.5rem, 7vw, 5rem);
}

.hero-watermark {
  position: absolute;
  inset: -20% -10%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0;
  pointer-events: none;
  transform: rotate(-7deg);
  font-family: var(--font-display);
  font-size: clamp(2.75rem, 12vw + 1rem, 8.5rem);
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.04em;
  color: var(--ink);
  opacity: 0.04;
  user-select: none;
  overflow: hidden;
}

.wm-row {
  display: flex;
  white-space: nowrap;
  will-change: transform;
}

.wm-track {
  flex-shrink: 0;
}

.wm-scroll-left .wm-track {
  animation: scroll-left 30s linear infinite;
}

.wm-scroll-right .wm-track {
  animation: scroll-right 30s linear infinite;
}

@keyframes scroll-left {
  0% { transform: translateX(0); }
  100% { transform: translateX(-100%); }
}

@keyframes scroll-right {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(0); }
}

.hero-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  max-width: min(40rem, 100%);
  box-sizing: border-box;
}

.hero-brand {
  width: 100%;
  margin: 0 0 clamp(1rem, 3vw, 1.5rem);
  padding: 0.06em 0 0.2em;
  box-sizing: border-box;
  font-family: var(--font-display);
  font-size: clamp(3rem, 17vw, 7.5rem);
  font-weight: 800;
  letter-spacing: -0.045em;
  line-height: 1.08;
  text-align: center;
  transform: translateY(-0.35rem);
  overflow: clip;
  /* Orange-only shimmer on the letters (same hue family as --pop) */
  background: linear-gradient(
    100deg,
    var(--pop) 0%,
    #ff8f78 22%,
    #ffd8ce 45%,
    var(--hero-shimmer-mid) 50%,
    #ffd8ce 55%,
    #ff8f78 78%,
    var(--pop) 100%
  );
  background-size: 220% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: hero-brand-shine 3.5s ease-in-out infinite;
}

@keyframes hero-brand-shine {
  0%,
  100% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
}

.hero-frame {
  position: relative;
  z-index: 1;
  width: 100%;
  text-align: center;
  padding: clamp(1.35rem, 4.5vw, 2.6rem) clamp(1rem, 3.5vw, 1.75rem);
  border: 1px solid var(--rose-line);
  border-radius: 4px;
  background: var(--bg-elevated);
  box-shadow:
    0 1px 0 var(--edge-inset) inset,
    0 32px 64px -36px rgb(0 0 0 / 0.65);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
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
  font-weight: var(--font-serif-weight);
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
  border: 1px solid var(--btn-ink-border);
  border-radius: 4px;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    transform 0.2s ease,
    color 0.2s ease;
}

.cta-primary:hover {
  background: var(--btn-ink-bg-hover);
  border-color: var(--btn-ink-border-hover);
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
  background: var(--surface-faint);
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
  font-weight: var(--font-mono-weight);
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

@media (max-width: 640px) {
  .hero {
    padding-top: clamp(4.5rem, 20vh, 12rem);
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

  .hero-brand {
    animation: none;
    background: var(--pop);
    -webkit-background-clip: unset;
    background-clip: unset;
    color: var(--pop);
  }
}
</style>

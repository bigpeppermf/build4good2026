import { clerkPlugin } from "@clerk/vue";
import { createApp } from "vue";
import "./index.css";
import App from "./App.vue";
import router from "./router";

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY?.trim();

function renderStartupError(title: string, details: string) {
  const root = document.querySelector<HTMLElement>("#app");
  if (!root) {
    return;
  }

  root.innerHTML = `
    <section style="min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f6efe4; color: #1f1a17;">
      <div style="width: min(36rem, 100%); border: 1px solid rgba(140, 72, 46, 0.22); background: #fffaf4; box-shadow: 0 24px 48px -32px rgba(0, 0, 0, 0.35); padding: 24px; border-radius: 6px;">
        <p style="margin: 0 0 12px; font: 600 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.08em; text-transform: uppercase; color: #8c482e;">
          Frontend startup error
        </p>
        <h1 style="margin: 0 0 12px; font: 700 32px/1.1 ui-sans-serif, system-ui, sans-serif;">
          ${title}
        </h1>
        <p style="margin: 0 0 12px; font: 400 16px/1.6 ui-sans-serif, system-ui, sans-serif; color: #4f433c;">
          ${details}
        </p>
        <p style="margin: 0; font: 400 14px/1.6 ui-sans-serif, system-ui, sans-serif; color: #6a5950;">
          Add <code>VITE_CLERK_PUBLISHABLE_KEY</code> to <code>frontend/.env.local</code> or <code>frontend/.env</code>, then restart Vite.
        </p>
      </div>
    </section>
  `;
}

if (!publishableKey) {
  console.error("Missing VITE_CLERK_PUBLISHABLE_KEY in the frontend environment.");
  renderStartupError(
    "Clerk publishable key is missing.",
    "The backend env is not exposed to Vite automatically, so the frontend could not initialize authentication.",
  );
} else {
  try {
    createApp(App)
      .use(clerkPlugin, { publishableKey })
      .use(router)
      .mount("#app");
  } catch (error) {
    console.error(error);
    renderStartupError(
      "The app failed to start.",
      "Check the browser console for the exact error. Clerk initialization is part of the startup path now.",
    );
  }
}

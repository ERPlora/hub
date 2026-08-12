// PWA: service worker registration, and nothing else.
//
// The hub IS an installable PWA — valid manifest, a service worker with a `fetch` handler, served
// over HTTPS — and every browser that supports installing offers it from its own UI: the icon in
// Chromium's address bar, «Add to Home Screen» on iOS Safari, the browser menu everywhere else.
//
// What used to live here was our own second offer on top of that one: we captured
// the browser's install event, kept the prompt, and re-served it as a dialog over the dashboard the
// moment anyone came in. hub#685 took that out (decision of 2026-08-10) — see
// `no-install-modal.test.ts` for the whole reasoning and for the guard that keeps it out. The
// installability is untouched; only the interruption is gone.

import { isTauri } from './device';

/** Registers the service worker. Idempotent. */
export function bootPwa(): void {
  if (typeof window === 'undefined') return;

  // The SW only helps in the PRODUCTION web-PWA deployment. It is NOT registered when:
  //   • Tauri (NATIVE app): its app-shell cache serves stale assets after the code changes.
  //   • DEV (Vite): Vite serves modules under moving URLs; the SW (stale-while-revalidate +
  //     index fallback on navigations) caches them stale or answers a module request with
  //     index.html → "Expected a JS module but got text/html" → a blank window.
  // In both cases we also UNREGISTER any service worker and empty its caches, so the browser stops
  // serving what a previous session left behind.
  if (isTauri() || import.meta.env.DEV) {
    if ('serviceWorker' in navigator) {
      void navigator.serviceWorker
        .getRegistrations()
        .then((regs) => regs.forEach((r) => void r.unregister()))
        .catch(() => {});
    }
    if ('caches' in window) {
      void caches.keys().then((keys) => keys.forEach((k) => void caches.delete(k))).catch(() => {});
    }
    return;
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch((err) => {
        console.warn('[pwa] could not register the service worker:', err);
      });
    });
  }
}

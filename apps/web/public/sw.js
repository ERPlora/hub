// Service Worker del Hub — mínimo y CSP-safe.
//
// Objetivo: que el Hub sea instalable como PWA (Chrome/Edge/Android exigen un SW con
// handler `fetch`) y que el app-shell aguante una caída de red puntual. NO es un SW de
// caché agresiva: los datos del POS van SIEMPRE a la red (runtime Axum) — aquí solo
// cacheamos el cascarón estático (navegaciones + assets con hash de Vite).
//
// Estrategia:
//   - Navegaciones (modo navigate): network-first con fallback al index cacheado (SPA offline).
//   - Assets estáticos same-origin (GET): stale-while-revalidate.
//   - API / WS / cross-origin: passthrough (nunca se cachean — los gestiona el runtime).
//
// El nombre de caché lleva versión: al cambiarlo, `activate` purga las viejas.

const CACHE = 'erplora-hub-shell-v1';
const APP_SHELL = '/';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.add(APP_SHELL)).catch(() => {}),
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

function isApiRequest(url) {
  return (
    url.pathname.startsWith('/api') ||
    url.pathname.startsWith('/ws') ||
    url.pathname.startsWith('/cloud') ||
    url.pathname.startsWith('/healthz')
  );
}

// #266 — los bundles de módulos (`/modules/<id>/dist/...`) NO llevan hash en su nombre: se
// reescriben in-place al reconstruir un módulo. Con SWR el SW serviría uno VIEJO en la primera
// carga aunque el servidor tuviera uno nuevo (y si el viejo tenía un bug, se reproducía). Van
// SIEMPRE a la red, como /api.
//
// hub#935 añadió la ruta versionada (`/modules/<id>/v/<version>/...`), que sí es inmutable y la
// cachea el navegador por `Cache-Control` un año. Aun así el SW se sigue apartando de TODO
// `/modules/`: la caché HTTP ya hace ese trabajo con la política que declara el runtime, y meter al
// SW en medio solo devolvería la clase de fallo mudo que la issue vino a cerrar.
function isUnversionedAsset(url) {
  return url.pathname.startsWith('/modules/');
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // Cross-origin, API/WS/health o assets sin hash (/modules/): lo gestiona la red/runtime, nunca el SW.
  if (url.origin !== self.location.origin || isApiRequest(url) || isUnversionedAsset(url)) return;

  // Navegaciones (SPA): red primero, fallback al index cacheado si no hay red.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(APP_SHELL, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(APP_SHELL).then((r) => r || Response.error())),
    );
    return;
  }

  // Assets estáticos: stale-while-revalidate.
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          if (res && res.status === 200 && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => cached);
      return cached || network;
    }),
  );
});

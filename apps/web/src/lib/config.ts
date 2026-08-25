// Config por entorno (Vite). En cloud/local los valores llegan por variables VITE_*.
// Nunca se hardcodean secretos aquí.
export const config = {
  // Cloud Portal URL (module catalogue, auth, billing, AI proxy). ARQUITECTURA.md §2.1–2.3.
  // Build-time value = FALLBACK only (dev/local). The runtime is the authority: `bootHubContext`
  // overwrites it with `cloud_base_url` from `GET /api/hub/context` (hub#1164) so one image serves
  // pre and prod. Anything that talks to the Cloud awaits `cloudApiUrlReady()` before reading it.
  cloudApiUrl: import.meta.env.VITE_CLOUD_API_URL ?? 'https://erplora.com',
  // X-Hub-Id del hub activo. Decisión del humano (2): NO hay picker de hub; el hub_id lo
  // inyecta el deployment y se RESUELVE EN EL BOOT desde el runtime (`GET /api/hub/context`,
  // ver lib/runtime.ts → bootHubContext, que lo sobreescribe). VITE_HUB_ID es solo fallback.
  hubId: (import.meta.env.VITE_HUB_ID as string | undefined) ?? '',
  // Modo demo: SOLO datos/credenciales ficticias para probar el flujo sin backend. Por defecto
  // OFF: en producción el login y las llamadas deben fallar de verdad. Se activa con VITE_DEMO=1.
  demo: (import.meta.env.VITE_DEMO ?? '0') === '1',
};

/** Hub id por defecto del runtime en dev/local (espejo de `crates/server` `DEV_HUB_ID`). */
export const DEV_HUB_ID = '00000000-0000-0000-0000-000000000001';

/**
 * ¿El hub corre en LOCAL/dev (sin un hub real gobernado por el Cloud)? (ADR-0064). Un
 * `hub_not_found` (410) del Cloud NO debe autoexpulsar a un hub local: se degrada a offline (el gate
 * de entitlement queda permisivo) en vez de hacer logout en bucle. `hubId` vacío = boot temprano sin
 * resolver → también permisivo. Un hub CLOUD real (uuid ≠ DEV) sí hace logout si el Cloud lo borra.
 */
export function isLocalHub(): boolean {
  return !config.hubId || config.hubId === DEV_HUB_ID;
}

// ── Cloud base URL resolution (hub#1164) ─────────────────────────────────────────────────────
// The login page can fire before `/api/hub/context` has answered. A request that raced ahead
// would go to the build-time URL — prod — and the hub's own CSP (built from the runtime's Cloud)
// would block it. So the resolution is a gate: while a boot is in flight, Cloud callers wait.

let cloudApiUrlPending: Promise<void> | null = null;
let settleCloudApiUrl: () => void = () => {};

/** Called when the boot fetch of `/api/hub/context` starts: Cloud callers now have to wait. */
export function markCloudApiUrlPending(): void {
  if (cloudApiUrlPending) return;
  cloudApiUrlPending = new Promise<void>((resolve) => {
    settleCloudApiUrl = resolve;
  });
}

/**
 * Called when the boot fetch ends, however it ended. A non-empty `cloud_base_url` becomes the
 * Cloud for this session; empty/absent (dev binary without Cloud, runtime down) keeps the
 * build-time fallback. Either way the gate opens: nothing waits on a runtime that already spoke.
 */
export function resolveCloudApiUrl(cloudBaseUrl: string | null | undefined): void {
  const url = typeof cloudBaseUrl === 'string' ? cloudBaseUrl.trim().replace(/\/+$/, '') : '';
  if (url) config.cloudApiUrl = url;
  settleCloudApiUrl();
  cloudApiUrlPending = null;
}

/**
 * Resolves once `config.cloudApiUrl` is authoritative for this session. Immediate when no boot is
 * in flight (before `main.ts` starts one, or after it ended); otherwise waits for the runtime.
 */
export function cloudApiUrlReady(): Promise<void> {
  return cloudApiUrlPending ?? Promise.resolve();
}

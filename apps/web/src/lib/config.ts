// Config por entorno (Vite). En cloud/local los valores llegan por variables VITE_*.
// Nunca se hardcodean secretos aquí.
export const config = {
  // URL del Cloud Portal (marketplace, auth, billing, proxy AI). ARQUITECTURA.md §2.1–2.3.
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

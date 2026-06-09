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

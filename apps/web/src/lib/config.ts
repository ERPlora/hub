// Config por entorno (Vite). En cloud/local los valores llegan por variables VITE_*.
// Nunca se hardcodean secretos aquí.
export const config = {
  // URL del Cloud Portal (marketplace, auth, billing, proxy AI). ARQUITECTURA.md §2.1–2.3.
  cloudApiUrl: import.meta.env.VITE_CLOUD_API_URL ?? 'https://erplora.com',
  // Hub actual (X-Hub-Id). En local/dev puede no estar.
  hubId: import.meta.env.VITE_HUB_ID ?? '',
  // Modo demo: si el Cloud no es accesible (sandbox), permite probar el flujo con datos locales.
  demo: (import.meta.env.VITE_DEMO ?? '1') === '1',
};

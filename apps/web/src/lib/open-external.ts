// Abre una URL en el navegador EXTERNO del usuario (deep-link de compra hacia el SaaS, docs…).
//
// El Hub es una PWA pura (sin shell Tauri; el Bridge es una app aparte): la URL se abre en una
// pestaña nueva con `noopener` (la página abierta no puede tocar `window.opener`).

/** Abre `url` en una pestaña nueva del navegador con `noopener`. */
export async function openExternal(url: string): Promise<void> {
  window.open(url, '_blank', 'noopener');
}

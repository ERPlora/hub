// PWA: registro del service worker + estado del botón «Instalar app».
//
// Chrome/Edge/Android disparan `beforeinstallprompt` cuando la PWA es instalable (manifest
// válido + SW con handler `fetch` + servida por HTTPS/localhost). Capturamos ese evento,
// guardamos el prompt diferido y exponemos `canInstall` para que el shell muestre el botón;
// `promptInstall()` lo dispara a petición del usuario (debe ser dentro de un gesto/click).
//
// iOS Safari no soporta `beforeinstallprompt` (la instalación es manual vía «Compartir →
// Añadir a inicio»); ahí el botón no aparece, que es el comportamiento esperado.

import { ref } from 'vue';

// `BeforeInstallPromptEvent` no está en lib.dom todavía; tipamos lo que usamos.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

let deferredPrompt: BeforeInstallPromptEvent | null = null;

/** `true` cuando el navegador ofrece instalar la PWA y aún no está instalada. */
export const canInstall = ref<boolean>(false);

/** `true` si la app ya corre en modo standalone (instalada). */
export const isStandalone = ref<boolean>(
  typeof window !== 'undefined' &&
    (window.matchMedia?.('(display-mode: standalone)').matches ||
      // iOS Safari expone navigator.standalone.
      (navigator as Navigator & { standalone?: boolean }).standalone === true),
);

/** Registra el service worker y engancha los eventos de instalación. Idempotente. */
export function bootPwa(): void {
  if (typeof window === 'undefined') return;

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch((err) => {
        console.warn('[pwa] no se pudo registrar el service worker:', err);
      });
    });
  }

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e as BeforeInstallPromptEvent;
    canInstall.value = true;
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    canInstall.value = false;
    isStandalone.value = true;
  });
}

/** Dispara el diálogo nativo de instalación. Devuelve `true` si el usuario aceptó. */
export async function promptInstall(): Promise<boolean> {
  if (!deferredPrompt) return false;
  await deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  deferredPrompt = null;
  canInstall.value = false;
  return outcome === 'accepted';
}

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

import { isTauri } from './device';

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

  // El SW solo aporta en el despliegue web-PWA de PRODUCCIÓN. NO se registra cuando:
  //   • Tauri (app NATIVA): su caché del app-shell sirve assets viejos tras cambiar código.
  //   • DEV (Vite): Vite sirve módulos con URLs cambiantes; el SW (stale-while-revalidate +
  //     fallback al index en navegaciones) los cachea rancios o devuelve index.html a una
  //     petición de módulo → "Expected a JS module but got text/html" → ventana en blanco.
  // En ambos casos, además, DESREGISTRAMOS cualquier SW y vaciamos sus cachés para que el
  // navegador deje de servir lo rancio de una sesión anterior.
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

// ── Modal «vista nativa» ────────────────────────────────────────────────────────────────────
// Sustituye al botón «Instalar app» del sidebar: al entrar, si la app no está instalada, se
// ofrece un modal con «Vista nativa» / «Cancelar» + checkbox «no volver a mostrar». Cancelar
// sin checkbox solo lo cierra esta vez (vuelve a ofrecerse en la siguiente entrada).

const LS_HIDE_MODAL_KEY = 'erplora.pwa.hideInstallModal';

/** Estado del modal (lo monta App.vue; lo abre `maybeShowInstallModal` al entrar). */
export const installModalOpen = ref<boolean>(false);

function installModalDismissedForever(): boolean {
  try {
    return localStorage.getItem(LS_HIDE_MODAL_KEY) === '1';
  } catch {
    return false;
  }
}

/** ¿Toca ofrecer el modal? No instalada (ni standalone ni Tauri) y no descartado para siempre. */
export function shouldShowInstallModal(): boolean {
  return !isTauri() && !isStandalone.value && !installModalDismissedForever();
}

/** Abre el modal si toca ofrecerlo. Llamar al entrar el usuario (post-login). */
export function maybeShowInstallModal(): void {
  if (shouldShowInstallModal()) installModalOpen.value = true;
}

/** Cierra el modal; con `remember` el descarte se persiste y no se vuelve a ofrecer. */
export function dismissInstallModal(remember: boolean): void {
  installModalOpen.value = false;
  if (remember) {
    try {
      localStorage.setItem(LS_HIDE_MODAL_KEY, '1');
    } catch {
      /* noop */
    }
  }
}

/** iOS (Safari/WebKit): sin `beforeinstallprompt`; la instalación es manual vía Compartir. */
export function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent)
    // iPadOS 13+ se presenta como macOS pero es táctil.
    || (navigator.userAgent.includes('Mac') && navigator.maxTouchPoints > 1);
}

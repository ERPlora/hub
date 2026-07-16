// @vitest-environment happy-dom
// Contrato del modal «usa la app en vista nativa» (PWA):
//   - Se OFRECE SIEMPRE al entrar mientras la app no esté instalada (no standalone, no Tauri)…
//   - …salvo que el usuario haya marcado «no volver a mostrar» (persistido en localStorage).
//   - «Cancelar» sin checkbox solo lo cierra esta vez: a la siguiente entrada vuelve a ofrecerse.
import { describe, it, expect, beforeEach, vi } from 'vitest';

// isTauri controlable por test (la web-pwa real devuelve false).
const tauriMock = vi.hoisted(() => ({ value: false }));
vi.mock('./device', () => ({
  isTauri: () => tauriMock.value,
}));

import {
  installModalOpen,
  isStandalone,
  shouldShowInstallModal,
  maybeShowInstallModal,
  dismissInstallModal,
} from './pwa';

const LS_KEY = 'erplora.pwa.hideInstallModal';

beforeEach(() => {
  localStorage.clear();
  tauriMock.value = false;
  isStandalone.value = false;
  installModalOpen.value = false;
});

describe('shouldShowInstallModal', () => {
  it('se ofrece cuando la app no está instalada y no se descartó', () => {
    expect(shouldShowInstallModal()).toBe(true);
  });

  it('NO se ofrece si la app ya corre standalone (instalada)', () => {
    isStandalone.value = true;
    expect(shouldShowInstallModal()).toBe(false);
  });

  it('NO se ofrece dentro del shell Tauri (ya es nativa)', () => {
    tauriMock.value = true;
    expect(shouldShowInstallModal()).toBe(false);
  });

  it('NO se ofrece si el usuario marcó «no volver a mostrar»', () => {
    localStorage.setItem(LS_KEY, '1');
    expect(shouldShowInstallModal()).toBe(false);
  });
});

describe('maybeShowInstallModal', () => {
  it('abre el modal cuando toca ofrecerlo', () => {
    maybeShowInstallModal();
    expect(installModalOpen.value).toBe(true);
  });

  it('no lo abre cuando no toca (standalone)', () => {
    isStandalone.value = true;
    maybeShowInstallModal();
    expect(installModalOpen.value).toBe(false);
  });
});

describe('dismissInstallModal', () => {
  it('cerrar SIN recordar: se vuelve a ofrecer en la siguiente entrada', () => {
    maybeShowInstallModal();
    dismissInstallModal(false);
    expect(installModalOpen.value).toBe(false);
    // Simula la siguiente entrada: vuelve a ofrecerse.
    expect(shouldShowInstallModal()).toBe(true);
  });

  it('cerrar CON «no volver a mostrar»: persiste y no se ofrece más', () => {
    maybeShowInstallModal();
    dismissInstallModal(true);
    expect(installModalOpen.value).toBe(false);
    expect(localStorage.getItem(LS_KEY)).toBe('1');
    expect(shouldShowInstallModal()).toBe(false);
  });
});

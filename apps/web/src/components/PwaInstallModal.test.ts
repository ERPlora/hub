// @vitest-environment happy-dom
// Contrato UI del modal PWA (sustituye al botón «Instalar app» del sidebar):
//   - Texto gancho + DOS botones («Vista nativa» / «Cancelar») + checkbox «no volver a mostrar».
//   - «Cancelar» cierra; si el checkbox está marcado, persiste el descarte (no se ofrece más).
//   - «Vista nativa» sin prompt nativo disponible (iOS/navegador sin soporte) → muestra
//     instrucciones de instalación manual en el propio modal.
import { describe, it, expect, beforeEach } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import PwaInstallModal from './PwaInstallModal.vue';
import { installModalOpen, isStandalone } from '../lib/pwa';

const LS_KEY = 'erplora.pwa.hideInstallModal';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      pwa: {
        title: 'Better as an app',
        hook: 'For the best experience, switch to the native view.',
        nativeView: 'Native view',
        cancel: 'Cancel',
        dontShowAgain: "Don't show this again",
        iosHint: 'Tap Share and then “Add to Home Screen”.',
        browserHint: 'Open your browser menu and choose “Install app”.',
      },
    },
  },
});

function mountModal() {
  // shallow: los ion-* se stubean; aquí se prueba el contrato del modal, no Ionic.
  return mount(PwaInstallModal, {
    shallow: true,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  });
}

beforeEach(() => {
  localStorage.clear();
  isStandalone.value = false;
  installModalOpen.value = true;
});

describe('PwaInstallModal', () => {
  it('pinta gancho, botones Vista nativa / Cancelar y el checkbox', () => {
    const w = mountModal();
    expect(w.find('[data-testid="pwa-hook"]').exists()).toBe(true);
    expect(w.find('[data-testid="pwa-native"]').exists()).toBe(true);
    expect(w.find('[data-testid="pwa-cancel"]').exists()).toBe(true);
    expect(w.find('[data-testid="pwa-remember"]').exists()).toBe(true);
  });

  it('Cancelar sin checkbox: cierra pero NO persiste el descarte', async () => {
    const w = mountModal();
    await w.find('[data-testid="pwa-cancel"]').trigger('click');
    expect(installModalOpen.value).toBe(false);
    expect(localStorage.getItem(LS_KEY)).toBeNull();
  });

  it('Cancelar con «no volver a mostrar» marcado: cierra Y persiste', async () => {
    const w = mountModal();
    // Emite ionChange desde el stub con el mismo shape que ion-checkbox (detail.checked).
    (w.getComponent('[data-testid="pwa-remember"]') as VueWrapper).vm.$emit(
      'ionChange',
      new CustomEvent('ionChange', { detail: { checked: true } }),
    );
    await w.vm.$nextTick();
    await w.find('[data-testid="pwa-cancel"]').trigger('click');
    expect(installModalOpen.value).toBe(false);
    expect(localStorage.getItem(LS_KEY)).toBe('1');
  });

  it('Vista nativa sin prompt nativo disponible → muestra instrucciones manuales', async () => {
    const w = mountModal();
    expect(w.find('[data-testid="pwa-instructions"]').exists()).toBe(false);
    await w.find('[data-testid="pwa-native"]').trigger('click');
    expect(w.find('[data-testid="pwa-instructions"]').exists()).toBe(true);
    // Sigue abierto para que el usuario pueda leerlas.
    expect(installModalOpen.value).toBe(true);
  });
});

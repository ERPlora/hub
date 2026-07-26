// @vitest-environment happy-dom
// Contrato del toggle "Presencia web pública" de Ajustes (ADR-0160): activa/desactiva la parte
// pública del hub (landing + páginas públicas) escribiendo la clave core `public.landing.visible`
// por la API de settings ya existente. El toggle DEBE reflejar el valor server-side actual y, al
// cambiarlo, persistirlo por el cliente de settings (mismo patrón que "Mostrar documentación de la
// API"). El cliente de settings se mockea; aquí se prueba el cableado del panel, no el fetch.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// HubIcon arrastra `~icons/…?raw` (denegado en test) → stub. Toast usa el controller de Ionic → stub.
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));

// Admin: el toggle solo lo cambia un admin (el runtime revalida). Aquí siempre admin.
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});

// Cliente de settings mockeado: `hubSettings` como ref reactiva controlable + `updateHubSettings`
// espía. Así el test controla el valor inicial y verifica la llamada de persistencia.
vi.mock('../lib/hub-settings', async () => {
  const { ref } = await import('vue');
  return { hubSettings: ref(null), updateHubSettings: vi.fn(async () => undefined) };
});

import PublicPresencePanel from './PublicPresencePanel.vue';
import { hubSettings, updateHubSettings, type HubSettings } from '../lib/hub-settings';

const TOGGLE = '[data-testid="public-presence-toggle"]';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      settings: {
        publicPresence: 'Public web presence',
        publicPresenceDesc: 'Turn on the public landing and pages',
        saved: 'Settings saved',
        saveError: 'Could not save settings',
      },
    },
  },
});

function makeSettings(overrides: Partial<HubSettings> = {}): HubSettings {
  return {
    currency: 'EUR',
    language: 'es',
    api_docs_enabled: false,
    country_code: 'ES',
    region_code: null,
    business_tax_id: '',
    business_legal_name: '',
    business_address: '',
    theme_palette: 'erplora',
    'public.landing.visible': false,
    ...overrides,
  };
}

function mountPanel() {
  // shallow: los ion-* se stubean; se prueba el cableado del toggle, no Ionic.
  return mount(PublicPresencePanel, {
    shallow: true,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  });
}

beforeEach(() => {
  vi.mocked(updateHubSettings).mockClear();
  hubSettings.value = makeSettings();
});

describe('PublicPresencePanel', () => {
  it('refleja el valor inicial ACTIVADO de la setting', () => {
    hubSettings.value = makeSettings({ 'public.landing.visible': true });
    const w = mountPanel();
    expect(w.get(TOGGLE).attributes('checked')).toBe('true');
  });

  it('refleja el valor inicial DESACTIVADO de la setting', () => {
    hubSettings.value = makeSettings({ 'public.landing.visible': false });
    const w = mountPanel();
    expect(w.get(TOGGLE).attributes('checked')).toBe('false');
  });

  it('al activarlo persiste `public.landing.visible = true` por la API de settings', async () => {
    hubSettings.value = makeSettings({ 'public.landing.visible': false });
    const w = mountPanel();
    (w.getComponent(TOGGLE) as VueWrapper).vm.$emit(
      'ionChange',
      new CustomEvent('ionChange', { detail: { checked: true } }),
    );
    await w.vm.$nextTick();
    expect(vi.mocked(updateHubSettings)).toHaveBeenCalledWith({ 'public.landing.visible': true });
  });

  it('al desactivarlo persiste `public.landing.visible = false`', async () => {
    hubSettings.value = makeSettings({ 'public.landing.visible': true });
    const w = mountPanel();
    (w.getComponent(TOGGLE) as VueWrapper).vm.$emit(
      'ionChange',
      new CustomEvent('ionChange', { detail: { checked: false } }),
    );
    await w.vm.$nextTick();
    expect(vi.mocked(updateHubSettings)).toHaveBeenCalledWith({ 'public.landing.visible': false });
  });
});

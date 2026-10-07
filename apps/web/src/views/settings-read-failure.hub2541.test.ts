// @vitest-environment happy-dom
// **Settings that could not be read are not painted, and nothing can be saved on top of them**
// (hub#2541).
//
// `GET /api/settings` failing used to be swallowed (`getHubSettings().catch(() => null)`): the
// screen seeded its fields with the defaults of the empty cache — Spain, EUR, Spanish — and showed
// them as the business's, with the instant selectors live and «Save changes» on the Business tab
// over an empty tax-id form. The pinpad card read its stops from the same empty cache.
//
// Now a failed read says so with Retry (the shared `ok-empty-state` of hub#2511) and the parts that
// depend on the read are not on screen until it works. The device's own cards (this device, other
// devices, hardware) do not depend on it and stay.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';

// Same seams as the neighbouring Settings tests (`settings-business-keeps-typed-on-failed-save.test.ts`).
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const route = { hash: '#hub', query: {} };
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => route,
}));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]) }));

const STORED = {
  currency: 'USD',
  language: 'en',
  api_docs_enabled: false,
  country_code: 'PT',
  timezone: null,
  business_tax_id: 'B12345674',
  business_legal_name: 'Lola SL',
  business_address: '',
  business_street: '',
  business_street_number: '',
  business_postal_code: '',
  business_city: '',
  business_identity_for_erplora_billing: false,
  theme_palette: 'erplora',
  pin_policy: 'never',
  pin_inactivity_minutes: 5,
};
const hubSettings = ref<Record<string, unknown> | null>(null);
const getHubSettings = vi.fn();
vi.mock('../lib/hub-settings', () => ({
  hubSettings,
  hubTimezone: () => 'Europe/Madrid',
  getHubSettings: () => getHubSettings(),
  updateHubSettings: vi.fn(),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/api-docs', () => ({ apiDocsEnabled: ref(false) }));
vi.mock('../lib/device', () => ({ isTauri: () => false }));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/money', () => ({ publishHubCurrency: vi.fn() }));
vi.mock('../lib/autostart', () => ({
  autostartState: vi.fn().mockResolvedValue({ available: false, enabled: false }),
  setAutostart: vi.fn(),
}));
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn() }));
vi.mock('../lib/runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({}),
  getClient: () => ({ query: vi.fn() }),
  listInstalledModules: vi.fn().mockResolvedValue([]),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  refreshHubTimezone: vi.fn(),
}));

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en } });

/** A stub that DOES render what it wraps (a plain stub drops its slot). */
const PASSTHROUGH = { template: '<div><slot /></div>' };

async function mountSettings(hash: '#hub' | '#business') {
  route.hash = hash;
  const SettingsPage = (await import('./SettingsPage.vue')).default;
  const wrapper = mount(SettingsPage, {
    shallow: true,
    global: {
      plugins: [i18n],
      stubs: {
        AppPage: PASSTHROUGH,
        IonCard: PASSTHROUGH,
        IonCardContent: PASSTHROUGH,
        IonList: PASSTHROUGH,
        IonItem: PASSTHROUGH,
        IonLabel: PASSTHROUGH,
        IonNote: PASSTHROUGH,
      },
    },
  });
  await flushPromises();
  return wrapper;
}

type Wrapper = Awaited<ReturnType<typeof mountSettings>>;
const has = (w: Wrapper, id: string) => w.find(`[data-testid="${id}"]`).exists();

const READ_DEPENDENT_GENERAL = [
  'settings-country',
  'settings-timezone',
  'settings-currency',
  'settings-hub-language',
  'settings-hub-palette',
  'settings-api-docs',
];

beforeEach(() => {
  hubSettings.value = null;
  getHubSettings.mockReset();
});

describe('Settings with the read down (hub#2541)', () => {
  it('🔴 General: says it could not load, with Retry, and paints no business setting nor the pinpad', async () => {
    getHubSettings.mockRejectedValue(new Error('settings → 503'));
    const wrapper = await mountSettings('#hub');

    expect(has(wrapper, 'settings-load-error')).toBe(true);
    expect(has(wrapper, 'settings-load-retry')).toBe(true);
    for (const id of READ_DEPENDENT_GENERAL) expect(has(wrapper, id), id).toBe(false);
    expect(wrapper.findComponent({ name: 'PinPolicyCard' }).exists(), 'the pinpad card').toBe(false);
    // What belongs to this device does not come from that read and stays.
    expect(wrapper.findComponent({ name: 'DeviceModeCard' }).exists()).toBe(true);
    expect(wrapper.findComponent({ name: 'DevicesCard' }).exists()).toBe(true);
    expect(has(wrapper, 'settings-hardware')).toBe(true);
  });

  it('🔴 Business: no tax-id form and no «Save changes» on top of what was not read', async () => {
    getHubSettings.mockRejectedValue(new Error('settings → 503'));
    const wrapper = await mountSettings('#business');

    expect(has(wrapper, 'settings-load-error')).toBe(true);
    expect(has(wrapper, 'settings-save-business')).toBe(false);
    expect(has(wrapper, 'settings-business-tax-id')).toBe(false);
  });

  it('🔴 a cache from an earlier read does not stand in for a read that just failed', async () => {
    hubSettings.value = { ...STORED };
    getHubSettings.mockRejectedValue(new Error('settings → 503'));
    const wrapper = await mountSettings('#business');

    expect(has(wrapper, 'settings-load-error')).toBe(true);
    expect(has(wrapper, 'settings-save-business')).toBe(false);
  });

  it('🔴 Retry reads again and, once it works, the form is back with the stored values', async () => {
    getHubSettings.mockRejectedValueOnce(new Error('settings → 503'));
    const wrapper = await mountSettings('#business');
    expect(has(wrapper, 'settings-save-business')).toBe(false);

    getHubSettings.mockImplementationOnce(async () => {
      hubSettings.value = { ...STORED };
      return hubSettings.value;
    });
    await wrapper.find('[data-testid="settings-load-retry"]').trigger('click');
    await flushPromises();

    expect(getHubSettings).toHaveBeenCalledTimes(2);
    expect(has(wrapper, 'settings-load-error')).toBe(false);
    expect(has(wrapper, 'settings-save-business')).toBe(true);
    expect((wrapper.vm as unknown as { businessTaxId: string }).businessTaxId).toBe('B12345674');
  });

  it('🔴 while the first read is on its way with nothing read before, it says it is loading and offers nothing', async () => {
    getHubSettings.mockReturnValue(new Promise(() => undefined));
    const wrapper = await mountSettings('#hub');

    expect(has(wrapper, 'settings-loading')).toBe(true);
    for (const id of READ_DEPENDENT_GENERAL) expect(has(wrapper, id), id).toBe(false);
    expect(has(wrapper, 'settings-load-error')).toBe(false);
  });

  it('while re-reading with values already read, the form stays (no flash on every visit)', async () => {
    hubSettings.value = { ...STORED };
    getHubSettings.mockReturnValue(new Promise(() => undefined));
    const wrapper = await mountSettings('#business');

    expect(has(wrapper, 'settings-save-business')).toBe(true);
    expect(has(wrapper, 'settings-loading')).toBe(false);
  });
});

// @vitest-environment happy-dom
// **The fiscal address is typed in parts** (hub#1846).
//
// Settings → Business kept the address as ONE free line, and official papers ask for it in parts:
// the tax authority's grant model reads «con domicilio fiscal en (municipio) … (vía pública) … nº …».
// With no parts to read, the VeriFactu app asked for the address AGAIN under the tax id and the
// legal name that already live here — and an address typed in two places ends up being two.
//
// So the address is written here once, in fields: street, number, postal code and city. The single
// line every invoice prints is composed from them by the runtime, and a business that never touches
// the fields keeps the line it typed (it is shown, so it is not silently lost).
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';

// Same seams as the neighbouring Settings tests (`settings-setup-refresh.test.ts`): the icon
// registry drags ~70 virtual `~icons/…?raw` ids this environment denies, and it has its own test.
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '#business', query: {} }),
}));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]) }));

const hubSettings = ref({
  currency: 'EUR',
  language: 'es',
  api_docs_enabled: false,
  country_code: 'ES',
  business_tax_id: '',
  business_legal_name: '',
  business_address: '',
  business_street: '',
  business_street_number: '',
  business_postal_code: '',
  business_city: '',
  theme_palette: 'erplora',
  pin_policy: 'never',
  pin_inactivity_minutes: 5,
} as Record<string, unknown>);
const updateHubSettings = vi.fn();
vi.mock('../lib/hub-settings', () => ({
  hubSettings,
  getHubSettings: vi.fn().mockResolvedValue({}),
  updateHubSettings: (...a: unknown[]) => updateHubSettings(...a),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/api-docs', () => ({ apiDocsEnabled: ref(false) }));
vi.mock('../lib/device', () => ({ isTauri: () => false }));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('../lib/toast', () => ({
  toastSuccess: (...a: unknown[]) => toastSuccess(...a),
  toastError: (...a: unknown[]) => toastError(...a),
}));
vi.mock('../lib/money', () => ({ publishHubCurrency: vi.fn() }));
vi.mock('../lib/autostart', () => ({
  autostartState: vi.fn().mockResolvedValue({ available: false, enabled: false }),
  setAutostart: vi.fn(),
}));
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn() }));

const client = { query: vi.fn() };
vi.mock('../lib/runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({}),
  getClient: () => client,
  listInstalledModules: vi.fn().mockResolvedValue([]),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  getBusinessCertificate: vi.fn().mockResolvedValue({ present: false }),
  publishFiscalIdentity: vi.fn(),
  putBusinessCertificate: vi.fn(),
  deleteBusinessCertificate: vi.fn(),
}));

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
});

/** A stub that DOES render what it wraps (a plain stub drops its slot). */
const PASSTHROUGH = { template: '<div><slot /></div>' };

async function mountBusinessTab() {
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

/** Presses «Save changes» on the Business tab. */
async function save(wrapper: Awaited<ReturnType<typeof mountBusinessTab>>): Promise<void> {
  const button = wrapper.find('[data-testid="settings-save-business"]');
  expect(button.exists(), 'the Business tab has no save button').toBe(true);
  await button.trigger('click');
  await flushPromises();
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  hubSettings.value = { ...hubSettings.value, fiscal_identity_publish_error: undefined };
  // The real client writes the runtime's answer into the cache; this seam does the same thing.
  updateHubSettings.mockReset().mockImplementation(async () => {
    hubSettings.value = { ...hubSettings.value };
    return hubSettings.value;
  });
  toastSuccess.mockReset();
  toastError.mockReset();
});

describe('Settings › Business · the fiscal address, in parts (hub#1846)', () => {
  it('asks for street, number, postal code and city — not for one free line', async () => {
    const wrapper = await mountBusinessTab();

    for (const id of [
      'settings-business-street',
      'settings-business-street-number',
      'settings-business-postal-code',
      'settings-business-city',
    ]) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), `the Business tab has no «${id}»`).toBe(true);
    }
    expect(
      wrapper.find('[data-testid="settings-business-address"]').exists(),
      'the free-text line is still editable: two addresses that can disagree',
    ).toBe(false);
  });

  it('saves the four parts, which is what the runtime composes the printed line from', async () => {
    const wrapper = await mountBusinessTab();
    const vm = wrapper.vm as unknown as {
      businessStreet: string;
      businessStreetNumber: string;
      businessPostalCode: string;
      businessCity: string;
    };
    vm.businessStreet = ' Rúa do Príncipe ';
    vm.businessStreetNumber = '10';
    vm.businessPostalCode = '36202';
    vm.businessCity = 'Vigo';

    await save(wrapper);

    expect(updateHubSettings).toHaveBeenCalledTimes(1);
    expect(updateHubSettings.mock.calls[0][0]).toMatchObject({
      business_street: 'Rúa do Príncipe',
      business_street_number: '10',
      business_postal_code: '36202',
      business_city: 'Vigo',
    });
    expect(updateHubSettings.mock.calls[0][0]).not.toHaveProperty('business_address');
  });

  // 🔴 A hub that typed its address as one line before this change must not see it vanish: the
  // fields are empty, and an empty form reads as «you have no address». The old line is shown.
  it('shows the old one-line address until the parts are filled, so it is not silently lost', async () => {
    hubSettings.value = { ...hubSettings.value, business_address: 'Calle Falsa 123, Madrid' };
    const wrapper = await mountBusinessTab();

    const legacy = wrapper.find('[data-testid="settings-business-address-legacy"]');
    expect(legacy.exists()).toBe(true);
    expect(legacy.text()).toContain('Calle Falsa 123, Madrid');
  });

  it('once the parts exist, the old line is not shown twice', async () => {
    hubSettings.value = {
      ...hubSettings.value,
      business_address: 'Rúa do Príncipe 10, 36202 Vigo',
      business_street: 'Rúa do Príncipe',
      business_city: 'Vigo',
    };
    const wrapper = await mountBusinessTab();

    expect(wrapper.find('[data-testid="settings-business-address-legacy"]').exists()).toBe(false);
  });
});

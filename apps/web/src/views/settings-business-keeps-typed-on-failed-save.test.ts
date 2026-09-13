// @vitest-environment happy-dom
// **A refused save on Settings → Business keeps what the admin typed.**
//
// Measured on `banco-pre` on 2026-09-13 (hub#1848): the admin filled in the fiscal address in parts,
// pressed «Save changes», the runtime said no, and every field went back to what the server had —
// empty. The toast explained the refusal, but the form she had just typed was gone, so fixing the
// one field that was wrong meant typing all six again.
//
// The instant settings (currency, palette, language) roll back on a refusal because the control IS
// the stored value. This is a form with an explicit «Save» button: until the save lands, what is on
// screen is her draft, and a refusal must leave the draft where it was — like every admin form does.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';

// Same seams as the neighbouring Settings tests (`settings-business-address-parts.hub1846.test.ts`):
// the icon registry drags ~70 virtual `~icons/…?raw` ids this environment denies.
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

const STORED = {
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
};
const hubSettings = ref({ ...STORED } as Record<string, unknown>);
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

type BusinessForm = {
  businessTaxId: string;
  businessLegalName: string;
  businessStreet: string;
  businessStreetNumber: string;
  businessPostalCode: string;
  businessCity: string;
};

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

/** Types the whole Business form, the way the admin on `banco-pre` did. */
function typeBusiness(wrapper: Awaited<ReturnType<typeof mountBusinessTab>>): BusinessForm {
  const vm = wrapper.vm as unknown as BusinessForm;
  vm.businessTaxId = 'B12345674';
  vm.businessLegalName = 'Peluquería Lola SL';
  vm.businessStreet = 'Rúa do Príncipe';
  vm.businessStreetNumber = '10';
  vm.businessPostalCode = '36202';
  vm.businessCity = 'Vigo';
  return vm;
}

/** Presses «Save changes» on the Business tab. */
async function save(wrapper: Awaited<ReturnType<typeof mountBusinessTab>>): Promise<void> {
  const button = wrapper.find('[data-testid="settings-save-business"]');
  expect(button.exists(), 'the Business tab has no save button').toBe(true);
  await button.trigger('click');
  await flushPromises();
}

function formOf(vm: BusinessForm): BusinessForm {
  return {
    businessTaxId: vm.businessTaxId,
    businessLegalName: vm.businessLegalName,
    businessStreet: vm.businessStreet,
    businessStreetNumber: vm.businessStreetNumber,
    businessPostalCode: vm.businessPostalCode,
    businessCity: vm.businessCity,
  };
}

const TYPED: BusinessForm = {
  businessTaxId: 'B12345674',
  businessLegalName: 'Peluquería Lola SL',
  businessStreet: 'Rúa do Príncipe',
  businessStreetNumber: '10',
  businessPostalCode: '36202',
  businessCity: 'Vigo',
};

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  hubSettings.value = { ...STORED };
  // The real client writes the runtime's answer into the cache; this seam does the same thing.
  updateHubSettings.mockReset().mockImplementation(async (partial: Record<string, unknown>) => {
    hubSettings.value = { ...hubSettings.value, ...partial };
    return hubSettings.value;
  });
  toastSuccess.mockReset();
  toastError.mockReset();
});

describe('Settings › Business · a refused save keeps the draft', () => {
  // The refusal has the shape `HubSettingsError` gives it: a stable code and the HTTP status.
  for (const [what, refusal] of [
    ['a 409 from the runtime', Object.assign(new Error('refused'), { code: 'business_tax_id_frozen', status: 409 })],
    ['a 422 on one bad value', Object.assign(new Error('invalid'), { code: 'invalid_setting', status: 422 })],
    ['the network dropping', new TypeError('Failed to fetch')],
  ] as const) {
    it(`🔴 keeps the six fields the admin typed after ${what}`, async () => {
      updateHubSettings.mockRejectedValue(refusal);

      const wrapper = await mountBusinessTab();
      const vm = typeBusiness(wrapper);
      await save(wrapper);

      expect(toastSuccess).not.toHaveBeenCalled();
      expect(toastError, 'the refusal is still explained').toHaveBeenCalledTimes(1);
      expect(formOf(vm), 'a refused save must not wipe what she typed').toEqual(TYPED);
      expect(hubSettings.value.business_street, 'and nothing was stored').toBe('');
    });
  }

  it('a save that landed shows what the runtime stored, not the draft', async () => {
    // The runtime normalises: a lower-case tax id comes back upper-case. The screen follows it.
    updateHubSettings.mockImplementation(async (partial: Record<string, unknown>) => {
      hubSettings.value = {
        ...hubSettings.value,
        ...partial,
        business_tax_id: String(partial.business_tax_id).toUpperCase(),
      };
      return hubSettings.value;
    });

    const wrapper = await mountBusinessTab();
    const vm = typeBusiness(wrapper);
    vm.businessTaxId = 'b12345674';
    await save(wrapper);

    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(formOf(vm)).toEqual(TYPED);
  });
});

// @vitest-environment happy-dom
// **«Use these details for my ERPlora invoice too» is a box of the form, not a button** (hub#2217).
//
// It was a toggle that published to ERPlora the moment it was pressed — with what was STORED, not
// what the owner had just typed — so a new business typing its tax id and ticking it before «Save
// changes» got «Could not share the details with ERPlora», the toggle stayed on anyway, and on the
// next visit it was off again because nothing remembered it.
//
// Now it behaves like every other field of the Business form: ticking it does nothing by itself,
// «Save changes» stores it with the rest (and the runtime tells ERPlora, hub-side), and it shows
// what was stored.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';
import { IonCheckbox } from '@ionic/vue';

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

const BOX = 'business_identity_for_erplora_billing';

/** The billing box, as the component that renders it. */
function box(wrapper: Awaited<ReturnType<typeof mountBusinessTab>>) {
  const found = wrapper
    .findAllComponents(IonCheckbox)
    .find((c) => c.attributes('data-testid') === 'settings-share-with-erplora');
  expect(found, 'the billing choice is a checkbox of the Business form').toBeTruthy();
  return found!;
}

/** Ticks (or unticks) the box the way Ionic does: the v-model update plus its change event. */
async function tick(wrapper: Awaited<ReturnType<typeof mountBusinessTab>>, checked: boolean): Promise<void> {
  const b = box(wrapper);
  b.vm.$emit('update:modelValue', checked);
  b.vm.$emit('ionChange', new CustomEvent('ionChange', { detail: { checked } }));
  await flushPromises();
}

const fetchMock = vi.fn(async () => new Response('{}', { status: 404 }));

beforeEach(() => {
  fetchMock.mockClear();
  vi.stubGlobal('fetch', fetchMock);
  hubSettings.value = {
    ...hubSettings.value,
    business_tax_id: '',
    business_legal_name: '',
    [BOX]: false,
    fiscal_identity_publish_error: undefined,
  };
  updateHubSettings.mockReset().mockImplementation(async (partial: Record<string, unknown>) => {
    hubSettings.value = { ...hubSettings.value, ...partial };
    return hubSettings.value;
  });
  toastSuccess.mockReset();
  toastError.mockReset();
});

describe('Settings › Business · the ERPlora-invoice box is part of the form (hub#2217)', () => {
  it('🔴 ticking the box sends nothing and says nothing', async () => {
    const wrapper = await mountBusinessTab();
    fetchMock.mockClear();

    await tick(wrapper, true);

    expect(updateHubSettings, 'ticking is not saving').not.toHaveBeenCalled();
    expect(fetchMock, 'ticking must not call anything').not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('🔴 «Save changes» stores the box with the rest of the business details', async () => {
    const wrapper = await mountBusinessTab();
    const vm = wrapper.vm as unknown as { businessTaxId: string; businessLegalName: string };
    vm.businessTaxId = 'B12345674';
    vm.businessLegalName = 'Bar Manolo SL';

    await tick(wrapper, true);
    await save(wrapper);

    expect(updateHubSettings).toHaveBeenCalledTimes(1);
    expect(updateHubSettings.mock.calls[0][0]).toMatchObject({
      business_tax_id: 'B12345674',
      business_legal_name: 'Bar Manolo SL',
      [BOX]: true,
    });
    expect(toastError).not.toHaveBeenCalled();
    expect(box(wrapper).props('modelValue'), 'the box stays ticked after the save').toBe(true);
  });

  it('🔴 an unticked box is saved as unticked', async () => {
    hubSettings.value = { ...hubSettings.value, business_tax_id: 'B12345674', [BOX]: true };
    const wrapper = await mountBusinessTab();

    await tick(wrapper, false);
    await save(wrapper);

    expect(updateHubSettings.mock.calls[0][0]).toMatchObject({ [BOX]: false });
  });

  it('🔴 shows what was stored, and follows the stored value when it changes', async () => {
    hubSettings.value = { ...hubSettings.value, [BOX]: true };
    const wrapper = await mountBusinessTab();
    expect(box(wrapper).props('modelValue'), 'a ticked box is remembered').toBe(true);

    hubSettings.value = { ...hubSettings.value, [BOX]: false };
    await flushPromises();
    expect(box(wrapper).props('modelValue')).toBe(false);
  });

  it('a refused save keeps the box as the owner left it', async () => {
    updateHubSettings.mockRejectedValue(new Error('403'));
    const wrapper = await mountBusinessTab();

    await tick(wrapper, true);
    await save(wrapper);

    expect(box(wrapper).props('modelValue'), 'a refused save must not undo the draft').toBe(true);
  });
});

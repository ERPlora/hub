// @vitest-environment happy-dom
// **Saving the business details and NOT reaching ERPlora is something she has to be told** (hub#1306).
//
// Saving the tax id publishes the fiscal identity to the control plane — that publication is what
// lets the dashboard name the *obligado* on the grant of representation (Annex I). It is
// best-effort by design: the settings are already stored, so a control plane that is down cannot
// cost the customer her save, and the runtime answers `200` with a stable code
// (`fiscal_identity_publish_error`) instead of a refusal.
//
// The failure mode that made hub#1306 expensive was silence. She saved, read «Saved», walked over
// to `…/fiscal/representation-grant/`, and found «set your tax details first» — the thing she had
// just done. Nothing on either screen could tell her that the save had worked and the sharing had
// not, so the only move left was to save again, and again.
//
// So: a save that published says nothing extra, and a save that did not says so out loud.
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

describe('Settings › Business · the save says whether ERPlora was told (hub#1306)', () => {
  it('🔴 says it out loud when the identity could not be published', async () => {
    updateHubSettings.mockImplementation(async () => {
      hubSettings.value = { ...hubSettings.value, fiscal_identity_publish_error: 'cloud_rejected' };
      return hubSettings.value;
    });

    const wrapper = await mountBusinessTab();
    await save(wrapper);

    // The save DID happen — she is not sent to type it all again.
    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(toastError, 'a failed publication cannot be silent').toHaveBeenCalledTimes(1);
    expect(toastError.mock.calls[0][0]).toBe(en.settings.shareWithErploraError);
  });

  it('says nothing extra when the identity did reach ERPlora', async () => {
    const wrapper = await mountBusinessTab();
    await save(wrapper);

    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(toastError, 'a save that worked has nothing to warn about').not.toHaveBeenCalled();
  });

  it('a refused save warns about the refusal, not about the sharing', async () => {
    // The identity never left because it was never stored: the one thing to say is the refusal.
    updateHubSettings.mockRejectedValue(new Error('403'));

    const wrapper = await mountBusinessTab();
    await save(wrapper);

    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledTimes(1);
    expect(toastError.mock.calls[0][0]).not.toBe(en.settings.shareWithErploraError);
  });
});

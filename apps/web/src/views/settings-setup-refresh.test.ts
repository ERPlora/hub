// @vitest-environment happy-dom
// **Saving the business details takes the ⛔ strip down — now, not when you happen to navigate**
// (hub#900).
//
// The blocking strip is a READ of `hub.setup.status` (ADR-0203, hub#374), and the two settings this
// screen writes — the tax id and the legal name — ARE the item behind it (`ITEM_BUSINESS_IDENTITY`
// in `crates/runtime/src/setup_status.rs`). Nothing re-read that document after a write, so the
// only triggers left were boot, a route change and `module.installed`: an owner filled in her
// business, pressed «Save changes», and «You cannot issue invoices yet» stayed on screen. The gate
// was already open — the strip was lying — and what she concluded was that she had failed to
// configure the one thing her till depends on.
//
// So what is pinned here is the invalidation, not the layout:
//   - a successful save re-reads the document, with the shell's client;
//   - it re-reads BEFORE telling her it saved, so the screen is true by the time she reads it;
//   - a refused save does not re-read: nothing changed, and a second read would only be noise;
//   - and every writer on this screen goes through the one door that does it, so the next setting
//     added here cannot quietly opt out.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';

// Same seams as the neighbouring Settings tests (`settings-print-coverage.test.ts`): the icon
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

const updateHubSettings = vi.fn();
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({
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
  }),
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

// The one query the strip reads. Mocked whole: what is under test is WHO asks for it and when.
const refreshSetupStatus = vi.fn();
vi.mock('../lib/setup-status', () => ({
  refreshSetupStatus: (...a: unknown[]) => refreshSetupStatus(...a),
}));

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
  updateHubSettings.mockReset().mockResolvedValue({});
  refreshSetupStatus.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
});

describe('Settings › Business · the strip clears itself when you save (hub#900)', () => {
  it('re-reads the configuration document after saving the business details', async () => {
    const wrapper = await mountBusinessTab();
    await save(wrapper);

    expect(updateHubSettings).toHaveBeenCalledTimes(1);
    // The screen that clears the ⛔ is the one that must invalidate it. Without this the strip
    // survives the save AND the reload, and only a navigation takes it down.
    expect(refreshSetupStatus, 'saving does not re-read `hub.setup.status`').toHaveBeenCalledTimes(1);
    expect(refreshSetupStatus).toHaveBeenCalledWith(client);
  });

  it('re-reads BEFORE saying it saved, so the screen is true when she reads the toast', async () => {
    const wrapper = await mountBusinessTab();
    await save(wrapper);

    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(
      refreshSetupStatus.mock.invocationCallOrder[0],
      'the "Saved" toast lands while the strip still says she cannot invoice',
    ).toBeLessThan(toastSuccess.mock.invocationCallOrder[0]);
  });

  it('a refused save does not re-read: nothing changed', async () => {
    updateHubSettings.mockRejectedValue(new Error('403'));
    const wrapper = await mountBusinessTab();
    await save(wrapper);

    expect(toastError).toHaveBeenCalledTimes(1);
    expect(refreshSetupStatus).not.toHaveBeenCalled();
  });
});

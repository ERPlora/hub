// @vitest-environment happy-dom
// hub#2519 — the version this hub runs comes from `GET /api/system`, which only an owner or an
// administrator may read (the event log it carries holds the tax agency's refusals, with customers'
// data). Apps compares that version with each app's floor before anyone presses «Install» (hub#2054)
// — and installing is an administrator's. For anybody else the screen must not ask: the runtime
// would refuse with 403 and the page would warn in the console, on every visit, about a check that
// is not theirs.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

const { admin, fetchSystemInfo } = await vi.hoisted(async () => {
  const vue = await import('vue');
  const admin = vue.ref(false);
  return {
    admin,
    // What the runtime answers: the version to an administrator, a refusal (`null`) to the rest.
    fetchSystemInfo: vi.fn(async () => (admin.value ? { hubVersion: 'v1.4.0' } : null)),
  };
});

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
// `lib/icons` bakes its SVGs through `~icons/…?raw`, which this environment denies (same cut as
// AppsPage.needs-newer-hub.hub2054.test.ts).
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/system', () => ({ fetchSystemInfo }));
vi.mock('../lib/cloud', () => ({ cloudMarketplaceModules: async () => [] }));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ on: () => () => {} }),
  requestInstall: vi.fn(),
  listInstalledModules: async () => [],
  activateModule: vi.fn(),
  deactivateModule: vi.fn(),
  uninstallModule: vi.fn(),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  InstallBlockedError: class InstallBlockedError extends Error {},
  ModuleActionError: class ModuleActionError extends Error {},
  updateModule: vi.fn(),
  listModuleUpdates: async () => [],
  listModuleVersions: async () => [],
  modulePublicationStatus: async () => null,
}));
vi.mock('../lib/nav', () => ({ moduleNav: { value: [] }, refreshModuleNav: vi.fn() }));
vi.mock('../lib/session', () => ({ isAdmin: admin }));
vi.mock('../lib/entitlement', () => ({
  isModuleEntitled: () => true,
  entitlementStatus: () => 'active',
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/setup-status', () => ({ setupStatus: ref(null), refreshSetupStatus: vi.fn() }));

import '@erplora/outfitkit/ok-data-table';
import AppsPage from './AppsPage.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

async function mountApps() {
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en, es },
  });
  const wrapper = mount(AppsPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
  await flushPromises();
  return wrapper;
}

// Every page mounted here watches the same `isAdmin`: one left alive would answer the next test.
enableAutoUnmount(afterEach);

let warn: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  admin.value = false;
  fetchSystemInfo.mockClear();
  warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  warn.mockRestore();
});

describe('the hub version Apps compares with each app floor (hub#2519)', () => {
  it('is not asked for by someone who does not administer the hub, and nothing is warned', async () => {
    await mountApps();

    expect(fetchSystemInfo).not.toHaveBeenCalled();
    const warned = warn.mock.calls.map((call: unknown[]) => String(call[0]));
    expect(warned.filter((message: string) => message.includes('hub version'))).toEqual([]);
  });

  it('is asked for by an owner or an administrator', async () => {
    admin.value = true;
    await mountApps();

    expect(fetchSystemInfo).toHaveBeenCalledTimes(1);
  });

  it('is asked for once the session resolves as an administrator after the page opened', async () => {
    await mountApps();
    expect(fetchSystemInfo).not.toHaveBeenCalled();

    admin.value = true;
    await flushPromises();

    expect(fetchSystemInfo).toHaveBeenCalledTimes(1);
  });
});

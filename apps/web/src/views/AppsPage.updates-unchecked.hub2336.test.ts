// @vitest-environment happy-dom
// Harness copied from the hub#2366 test. hub#2336 — the runtime answers `ok: true` with every app
// `checked: false` when the marketplace did not answer: «My apps» must read that as «could not
// check» (the hub#2366 warning with «Retry»), not as «everything is up to date», and must tell the
// bell the same. Original header of the harness: ERPlora/hub#2366 — in «My apps», when the hub could not ask the marketplace
// which apps have a new version (offline, marketplace down or slow), the screen looked exactly like
// «everything is up to date»: no «Update» on the rows, no «Update all», no word. The owner believed
// their apps were current when nobody had been able to check.
//
// What this pins, on the wiring of AppsPage itself:
//   · a failed check paints its own warning («could not check») with «Retry» — distinct from a
//     check that answered «nothing new», which paints nothing;
//   · nothing is painted while the first check is still on its way (loading is not failing);
//   · «Retry» asks again: an answer clears the warning and brings the updates it found; another
//     failure keeps the warning; the button cannot fire twice while the question is out;
//   · a failed check still offers no «Update all» (hub#516: a failure never becomes an offer);
//   · like «Update all», it is for whoever can update: a non-admin does not see it.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const { listModuleUpdates, admin, wsHandlers, publishModuleUpdates, markModuleUpdatesUnknown } = vi.hoisted(() => ({
  listModuleUpdates: vi.fn(),
  publishModuleUpdates: vi.fn(),
  markModuleUpdatesUnknown: vi.fn(),
  admin: { value: true },
  wsHandlers: new Map<string, (payload: unknown) => void>(),
}));

let INSTALLED: Array<Record<string, unknown>> = [];

vi.mock('../lib/system', () => ({ fetchSystemInfo: async () => ({ hubVersion: 'v1.4.0' }) }));
vi.mock('../lib/cloud', () => ({ cloudMarketplaceModules: async () => [] }));
vi.mock('../lib/module-loader', () => ({ reloadForModuleUpdate: vi.fn() }));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({
    on: (event: string, handler: (payload: unknown) => void) => {
      wsHandlers.set(event, handler);
      return () => wsHandlers.delete(event);
    },
  }),
  requestInstall: vi.fn(),
  listInstalledModules: async () => INSTALLED,
  activateModule: vi.fn(),
  deactivateModule: vi.fn(),
  uninstallModule: vi.fn(),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  InstallBlockedError: class InstallBlockedError extends Error {
    blockedOn: string[];
    constructor(message: string, blockedOn: string[]) {
      super(message);
      this.blockedOn = blockedOn;
    }
  },
  ModuleActionError: class ModuleActionError extends Error {},
  updateModule: vi.fn(),
  listModuleUpdates: () => listModuleUpdates(),
  listModuleVersions: vi.fn(async () => ({ versions: ['2.0.0'] })),
  modulePublicationStatus: async () => null,
}));
vi.mock('../lib/nav', () => ({ moduleNav: { value: [] }, refreshModuleNav: vi.fn() }));
vi.mock('../lib/session', async () => {
  const { ref: vueRef } = await import('vue');
  const isAdmin = vueRef(true);
  Object.defineProperty(admin, 'value', {
    get: () => isAdmin.value,
    set: (v: boolean) => {
      isAdmin.value = v;
    },
  });
  return { isAdmin };
});
vi.mock('../lib/entitlement', () => ({
  isModuleEntitled: () => true,
  entitlementStatus: () => 'active',
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/module-update-notice', () => ({
  publishModuleUpdates: (...args: unknown[]) => publishModuleUpdates(...args),
  markModuleUpdatesUnknown: () => markModuleUpdatesUnknown(),
}));
vi.mock('../lib/setup-status', () => ({ setupStatus: ref(null), refreshSetupStatus: vi.fn() }));

import '@erplora/outfitkit/ok-data-table';
import AppsPage from './AppsPage.vue';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const mounted: Array<{ unmount: () => void }> = [];

function mountApps(locale: 'en' | 'es' = 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(AppsPage, { global: { plugins: [i18n], renderStubDefaultSlot: true }, shallow: true });
  mounted.push(wrapper);
  return wrapper;
}
type Wrapper = ReturnType<typeof mountApps>;

async function settle(): Promise<void> {
  for (let i = 0; i < 3; i += 1) {
    await flushPromises();
    await nextTick();
  }
}

/** What the page paints, without the tags (a stubbed ion-* keeps its slot text). */
const painted = (w: Wrapper, selector: string): string => {
  const found = w.find(selector);
  return found.exists()
    ? found
        .html()
        .replace(/<[^>]*>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
    : '';
};
const warning = (w: Wrapper) => w.find('[data-testid="apps-updates-check-failed"]');
const retry = (w: Wrapper) => w.find('[data-testid="apps-updates-check-retry"]');
const offer = (w: Wrapper) => w.find('[data-testid="apps-update-all"]');

const offline = () => Promise.reject(new Error('GET /api/modules/updates → 502'));
const upd = (id: string, over: Record<string, unknown> = {}) => ({
  module_id: id,
  installed: '1.0.0',
  latest: '2.0.0',
  update_available: true,
  pinned: null,
  ...over,
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});
beforeEach(() => {
  admin.value = true;
  wsHandlers.clear();
  listModuleUpdates.mockReset();
  publishModuleUpdates.mockReset();
  markModuleUpdatesUnknown.mockReset();
  INSTALLED = [
    { id: 'sales', name: 'Sales', version: '1.0.0', status: 'active' },
    { id: 'inventory', name: 'Inventory', version: '1.0.0', status: 'active' },
  ];
});

/** A row the runtime could not ask the marketplace about. */
const unchecked = (id: string) => upd(id, { latest: '1.0.0', update_available: false, checked: false });

describe('«My apps» reads «the marketplace did not answer» as «could not check» (hub#2336)', () => {
  it('🔴 every app unchecked paints the «could not check» warning with «Retry»', async () => {
    listModuleUpdates.mockImplementation(async () => [unchecked('sales'), unchecked('inventory')]);
    const w = mountApps();
    await settle();
    expect(warning(w).exists(), '«did not answer» must not look like «up to date»').toBe(true);
    expect(painted(w, '[data-testid="apps-updates-check-failed"]')).toContain(enCatalogue.apps.updatesCheckFailed);
    expect(retry(w).exists()).toBe(true);
    expect(offer(w).exists()).toBe(false);
  });

  it('says it in Spanish too', async () => {
    listModuleUpdates.mockImplementation(async () => [unchecked('sales'), unchecked('inventory')]);
    const w = mountApps('es');
    await settle();
    expect(painted(w, '[data-testid="apps-updates-check-failed"]')).toContain(esCatalogue.apps.updatesCheckFailed);
  });

  it('🔴 one app unchecked is enough to say it, and the update found for the other is still offered', async () => {
    listModuleUpdates.mockImplementation(async () => [upd('sales'), unchecked('inventory')]);
    const w = mountApps();
    await settle();
    expect(warning(w).exists()).toBe(true);
    expect(offer(w).exists(), 'a known update is news whatever happened to the other app').toBe(true);
  });

  it('every app checked and current paints no warning', async () => {
    listModuleUpdates.mockImplementation(async () => [
      upd('sales', { installed: '2.0.0', update_available: false, checked: true }),
      upd('inventory', { installed: '2.0.0', update_available: false, checked: true }),
    ]);
    const w = mountApps();
    await settle();
    expect(warning(w).exists()).toBe(false);
  });

  it('«Retry» that gets an answer clears the warning', async () => {
    listModuleUpdates
      .mockImplementationOnce(async () => [unchecked('sales'), unchecked('inventory')])
      .mockImplementation(async () => [upd('sales'), upd('inventory')]);
    const w = mountApps();
    await settle();
    expect(warning(w).exists()).toBe(true);
    await retry(w).trigger('click');
    await settle();
    expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    expect(warning(w).exists()).toBe(false);
    expect(offer(w).exists()).toBe(true);
  });

  it('«Retry» answered unchecked again keeps the warning', async () => {
    listModuleUpdates.mockImplementation(async () => [unchecked('sales'), unchecked('inventory')]);
    const w = mountApps();
    await settle();
    await retry(w).trigger('click');
    await settle();
    expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    expect(warning(w).exists()).toBe(true);
  });

  // The bell reads the same answer: it keeps its count and says it could not check.
  it('🔴 hands the unchecked answer to the bell', async () => {
    const answer = [upd('sales'), unchecked('inventory')];
    listModuleUpdates.mockImplementation(async () => answer);
    mountApps();
    await settle();
    expect(publishModuleUpdates).toHaveBeenCalled();
    expect(publishModuleUpdates.mock.calls.at(-1)?.[0]).toEqual(answer);
  });

  it('🔴 a check that failed outright tells the bell it could not check', async () => {
    listModuleUpdates.mockImplementation(offline);
    mountApps();
    await settle();
    expect(markModuleUpdatesUnknown).toHaveBeenCalledTimes(1);
    expect(publishModuleUpdates).not.toHaveBeenCalled();
  });
});

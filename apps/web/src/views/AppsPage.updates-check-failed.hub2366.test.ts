// @vitest-environment happy-dom
// Regression test for ERPlora/hub#2366 — in «My apps», when the hub could not ask the marketplace
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

const { listModuleUpdates, admin, wsHandlers } = vi.hoisted(() => ({
  listModuleUpdates: vi.fn(),
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

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

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
  INSTALLED = [
    { id: 'sales', name: 'Sales', version: '1.0.0', status: 'active' },
    { id: 'inventory', name: 'Inventory', version: '1.0.0', status: 'active' },
  ];
});

describe('«My apps» says when it could not check for new versions (hub#2366)', () => {
  it('🔴 a failed check paints a warning with «Retry»', async () => {
    listModuleUpdates.mockImplementation(offline);
    const w = mountApps();
    await settle();
    expect(warning(w).exists(), 'the failed check must be visible on the screen').toBe(true);
    expect(warning(w).attributes('tone')).toBe('warning');
    expect(painted(w, '[data-testid="apps-updates-check-failed"]')).toContain(enCatalogue.apps.updatesCheckFailed);
    expect(painted(w, '[data-testid="apps-updates-check-retry"]')).toBe(enCatalogue.apps.retryCatalog);
    // hub#516: a failure never becomes an offer.
    expect(offer(w).exists()).toBe(false);
  });

  it('says it in Spanish too', async () => {
    listModuleUpdates.mockImplementation(offline);
    const w = mountApps('es');
    await settle();
    expect(painted(w, '[data-testid="apps-updates-check-failed"]')).toContain(esCatalogue.apps.updatesCheckFailed);
    expect(painted(w, '[data-testid="apps-updates-check-retry"]')).toBe(esCatalogue.apps.retryCatalog);
  });

  it('🔴 a check that answered «nothing new» paints no warning (up to date ≠ could not check)', async () => {
    listModuleUpdates.mockImplementation(async () => [
      upd('sales', { installed: '2.0.0', update_available: false }),
      upd('inventory', { installed: '2.0.0', update_available: false }),
    ]);
    const w = mountApps();
    await settle();
    expect(warning(w).exists()).toBe(false);
    expect(offer(w).exists()).toBe(false);
  });

  it('paints nothing while the first check is still on its way', async () => {
    const pending = deferred<unknown[]>();
    listModuleUpdates.mockImplementation(() => pending.promise);
    const w = mountApps();
    await settle();
    expect(warning(w).exists(), 'loading is not failing').toBe(false);
    pending.resolve([]);
    await settle();
    expect(warning(w).exists()).toBe(false);
  });

  it('🔴 «Retry» asks again and, with an answer, the warning goes and the updates it found show', async () => {
    listModuleUpdates.mockImplementationOnce(offline).mockImplementation(async () => [upd('sales'), upd('inventory')]);
    const w = mountApps();
    await settle();
    expect(warning(w).exists()).toBe(true);
    await retry(w).trigger('click');
    await settle();
    expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    expect(warning(w).exists(), 'answered: the warning must go').toBe(false);
    expect(offer(w).exists(), 'the updates the retry found are offered').toBe(true);
  });

  it('keeps the warning when «Retry» fails again', async () => {
    listModuleUpdates.mockImplementation(offline);
    const w = mountApps();
    await settle();
    await retry(w).trigger('click');
    await settle();
    expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    expect(warning(w).exists()).toBe(true);
  });

  it('«Retry» cannot fire twice while the question is out', async () => {
    listModuleUpdates.mockImplementationOnce(offline);
    const w = mountApps();
    await settle();
    // The stub paints the prop as text: «false» while it can be pressed, «true» while it cannot.
    expect(retry(w).attributes('disabled'), 'the button can be pressed after the failure').not.toBe('true');
    const pending = deferred<unknown[]>();
    listModuleUpdates.mockImplementation(() => pending.promise);
    await retry(w).trigger('click');
    await settle();
    expect(retry(w).attributes('disabled'), 'the button is off while retrying').toBe('true');
    await retry(w).trigger('click');
    await settle();
    expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    pending.resolve([]);
    await settle();
    expect(warning(w).exists()).toBe(false);
  });

  it('a later failed check (another tab installed an app) brings the warning back', async () => {
    listModuleUpdates.mockImplementationOnce(async () => []).mockImplementation(offline);
    const w = mountApps();
    await settle();
    expect(warning(w).exists()).toBe(false);
    const installed = wsHandlers.get('module.installed');
    expect(installed, 'AppsPage listens to module.installed').toBeDefined();
    installed?.({ module_id: 'inventory' });
    await settle();
    expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    expect(warning(w).exists()).toBe(true);
  });

  it('belongs to «My apps»: the catalog tabs do not show it', async () => {
    listModuleUpdates.mockImplementation(offline);
    const w = mountApps();
    await settle();
    expect(warning(w).exists()).toBe(true);
    (w.vm as unknown as { tab: string }).tab = 'all';
    await settle();
    expect(warning(w).exists()).toBe(false);
  });

  it('is not shown to someone who cannot update apps', async () => {
    admin.value = false;
    listModuleUpdates.mockImplementation(offline);
    const w = mountApps();
    await settle();
    expect(warning(w).exists()).toBe(false);
  });

  it('en and es both carry the sentence and the button', () => {
    expect(enCatalogue.apps.updatesCheckFailed).toBeTruthy();
    expect(esCatalogue.apps.updatesCheckFailed).toBeTruthy();
    expect(esCatalogue.apps.updatesCheckFailed).not.toBe(enCatalogue.apps.updatesCheckFailed);
  });
});

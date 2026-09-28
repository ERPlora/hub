// @vitest-environment happy-dom
// Regression test for ERPlora/hub#2331 — in «My apps», an owner with nine apps behind had to press
// «Update» on each row and wait for it before the next. Every app store offers «Update all».
//
// What this pins, on the wiring of AppsPage itself:
//   · the offer shows when at least ONE app has a new version the owner can apply (not the ones
//     that need a newer ERPlora, hub#2082), and never for a non-admin;
//   · it rides the SAME per-app update the row button uses (`updateModule(id, '')`, one after
//     another, no version picker), saying which app is running and how far it got;
//   · all good → the page reloads ONCE to run the new versions (hub#935);
//   · a failure says which app and why, the others still update, the failed one can be retried,
//     and the page does not reload under the person's feet while they read it.
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

const { updateModule, listModuleVersions, reloadForModuleUpdate, admin } = vi.hoisted(() => ({
  updateModule: vi.fn(),
  listModuleVersions: vi.fn(async (_id: string) => ({ versions: ['2.0.0', '1.5.0'] })),
  reloadForModuleUpdate: vi.fn(),
  admin: { value: true },
}));

let INSTALLED: Array<Record<string, unknown>> = [];
let UPDATES: Array<Record<string, unknown>> = [];

vi.mock('../lib/system', () => ({ fetchSystemInfo: async () => ({ hubVersion: 'v1.4.0' }) }));
vi.mock('../lib/cloud', () => ({ cloudMarketplaceModules: async () => [] }));
vi.mock('../lib/module-loader', () => ({ reloadForModuleUpdate }));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ on: () => () => {} }),
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
  updateModule: (id: string, version?: string) => updateModule(id, version),
  listModuleUpdates: async () => UPDATES,
  listModuleVersions: (id: string) => listModuleVersions(id),
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
import * as runtime from '../lib/runtime';

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
const offer = (w: Wrapper) => w.find('[data-testid="apps-update-all"]');
const plural = (s: string, n: number) => {
  const [one, many] = s.split('|').map((p) => p.trim());
  return (n === 1 ? one : many).replace('{n}', String(n));
};
const fill = (s: string, params: Record<string, string | number>) =>
  Object.entries(params).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(String(v)), s);

async function pressUpdateAll(w: Wrapper): Promise<void> {
  const button = w.find('[data-testid="apps-update-all-button"]');
  expect(button.exists(), '«Update all» must be on screen').toBe(true);
  await button.trigger('click');
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const ok = (id: string) => ({ ok: true, module_id: id, from: '1.0.0', to: '2.0.0', updated: true });
const failure = (sentence: string) => Object.assign(new Error(`update → 502`), { detail: sentence });

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});
beforeEach(() => {
  admin.value = true;
  updateModule.mockReset();
  listModuleVersions.mockClear();
  reloadForModuleUpdate.mockClear();
  INSTALLED = [
    { id: 'sales', name: 'Sales', version: '1.0.0', status: 'active' },
    { id: 'inventory', name: 'Inventory', version: '1.0.0', status: 'active' },
    { id: 'future', name: 'Future', version: '1.0.0', status: 'active' },
    { id: 'current', name: 'Current', version: '2.0.0', status: 'active' },
  ];
  const upd = (id: string, over: Record<string, unknown> = {}) => ({
    module_id: id,
    installed: '1.0.0',
    latest: '2.0.0',
    update_available: true,
    pinned: null,
    ...over,
  });
  UPDATES = [
    upd('sales'),
    upd('inventory'),
    // Needs a newer ERPlora (hub#2082): its row does not offer «Update», so neither does the batch.
    upd('future', { latest_min_erplora_version: '9.9.9' }),
    upd('current', { installed: '2.0.0', update_available: false }),
  ];
});

describe('«Update all» in «My apps» (hub#2331)', () => {
  it('🔴 offers it with how many apps have a new version', async () => {
    const w = mountApps();
    await settle();
    expect(offer(w).exists()).toBe(true);
    expect(painted(w, '[data-testid="apps-update-all"]')).toContain(plural(enCatalogue.apps.updateAllOffer, 2));
    expect(painted(w, '[data-testid="apps-update-all-button"]')).toBe(enCatalogue.apps.updateAllAction);
  });

  it('says it in Spanish too', async () => {
    const w = mountApps('es');
    await settle();
    expect(painted(w, '[data-testid="apps-update-all"]')).toContain(plural(esCatalogue.apps.updateAllOffer, 2));
    expect(painted(w, '[data-testid="apps-update-all-button"]')).toBe(esCatalogue.apps.updateAllAction);
  });

  it('offers it for a single app with a new version too', async () => {
    UPDATES = UPDATES.filter((u) => u.module_id !== 'inventory');
    const w = mountApps();
    await settle();
    expect(painted(w, '[data-testid="apps-update-all"]')).toContain(plural(enCatalogue.apps.updateAllOffer, 1));
    // The singular only — not the whole «one | many» message.
    expect(painted(w, '[data-testid="apps-update-all"]')).not.toContain('|');
  });

  it('is not there when nothing can be updated, nor for a non-admin', async () => {
    UPDATES = UPDATES.filter((u) => u.module_id === 'future' || u.module_id === 'current');
    let w = mountApps();
    await settle();
    expect(offer(w).exists()).toBe(false);

    UPDATES = [{ module_id: 'sales', installed: '1.0.0', latest: '2.0.0', update_available: true, pinned: null }];
    admin.value = false;
    w = mountApps();
    await settle();
    expect(offer(w).exists()).toBe(false);
  });

  it("🔴 updates each app in turn through the row's own update, says where it is, and reloads once", async () => {
    const first = deferred<ReturnType<typeof ok>>();
    const second = deferred<ReturnType<typeof ok>>();
    updateModule.mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise);
    const w = mountApps();
    await settle();

    await pressUpdateAll(w);
    await settle();
    expect(updateModule.mock.calls).toEqual([['sales', '']]);
    expect(painted(w, '[data-testid="apps-update-all"]')).toContain(
      fill(enCatalogue.apps.updateAllProgress, { name: 'Sales', current: 1, total: 2 }),
    );
    expect(w.find('[data-testid="apps-update-all-button"]').exists(), 'no second batch while one runs').toBe(false);

    first.resolve(ok('sales'));
    await settle();
    expect(updateModule.mock.calls).toEqual([
      ['sales', ''],
      ['inventory', ''],
    ]);
    expect(painted(w, '[data-testid="apps-update-all"]')).toContain(
      fill(enCatalogue.apps.updateAllProgress, { name: 'Inventory', current: 2, total: 2 }),
    );
    expect(reloadForModuleUpdate).not.toHaveBeenCalled();

    second.resolve(ok('inventory'));
    await settle();
    // No version picker: the batch takes what the runtime resolves, like the start-up updater.
    expect(listModuleVersions).not.toHaveBeenCalled();
    expect(reloadForModuleUpdate).toHaveBeenCalledTimes(1);
  });

  it('🔴 a failed app says why, the rest still update, it can be retried, and the page waits for the owner', async () => {
    const sentence = 'The marketplace did not answer in time';
    updateModule
      .mockImplementationOnce(async () => {
        throw failure(sentence);
      })
      .mockImplementationOnce(async () => ok('inventory'));
    const w = mountApps();
    await settle();

    await pressUpdateAll(w);
    await settle();
    expect(updateModule.mock.calls).toEqual([
      ['sales', ''],
      ['inventory', ''],
    ]);
    // Reloading now would wipe the reason off the screen before anyone read it.
    expect(reloadForModuleUpdate).not.toHaveBeenCalled();

    const text = painted(w, '[data-testid="apps-update-all"]');
    expect(text).toContain(fill(enCatalogue.apps.updateAllSummary, { updated: 1, total: 2 }));
    expect(painted(w, '[data-testid="apps-update-all-result"][data-id="sales"]')).toContain('Sales');
    expect(painted(w, '[data-testid="apps-update-all-result"][data-id="sales"]')).toContain(sentence);
    expect(painted(w, '[data-testid="apps-update-all-result"][data-id="inventory"]')).toContain('1.0.0 → 2.0.0');
    expect(w.find('[data-testid="apps-update-all-retry"][data-id="inventory"]').exists()).toBe(false);
    expect(painted(w, '[data-testid="apps-update-all-finish"]')).toBe(enCatalogue.apps.updateAllReload);

    // Retry the one that failed: the same update, for that app only.
    updateModule.mockImplementationOnce(async () => ok('sales'));
    await w.find('[data-testid="apps-update-all-retry"][data-id="sales"]').trigger('click');
    await settle();
    expect(updateModule.mock.calls.at(-1)).toEqual(['sales', '']);
    expect(updateModule).toHaveBeenCalledTimes(3);
    // Nothing failed any more: the page reloads to run the new versions, as after a single update.
    expect(reloadForModuleUpdate).toHaveBeenCalledTimes(1);
  });

  it('🔴 with a failure on screen, «My apps» already shows the new version of the apps that did update', async () => {
    updateModule
      .mockImplementationOnce(async () => {
        throw failure('down');
      })
      .mockImplementationOnce(async () => {
        // What the runtime answers from now on: inventory runs 2.0.0 and has nothing newer.
        INSTALLED = INSTALLED.map((m) => (m.id === 'inventory' ? { ...m, version: '2.0.0' } : m));
        UPDATES = UPDATES.map((u) =>
          u.module_id === 'inventory' ? { ...u, installed: '2.0.0', update_available: false } : u,
        );
        return ok('inventory');
      });
    const w = mountApps();
    await settle();
    await pressUpdateAll(w);
    await settle();
    expect(reloadForModuleUpdate).not.toHaveBeenCalled();

    const table = w
      .findAll('ok-data-table')
      .map((t) => t.element as HTMLElement & { rows?: Array<Record<string, unknown>> })
      .find((t) => (t.rows ?? []).some((r) => r.id === 'inventory' && 'status' in r))!;
    const inventory = table.rows!.find((r) => r.id === 'inventory')!;
    expect(inventory.version).toBe('2.0.0');
    expect(inventory.update).toBeNull();
  });

  it('a paid dependency blocking one app is said in those words (ADR-0060)', async () => {
    const Blocked = runtime.InstallBlockedError as unknown as new (m: string, b: string[]) => Error;
    updateModule
      .mockImplementationOnce(async () => {
        throw new Blocked('blocked', ['loyalty']);
      })
      .mockImplementationOnce(async () => ok('inventory'));
    const w = mountApps();
    await settle();
    await pressUpdateAll(w);
    await settle();
    expect(painted(w, '[data-testid="apps-update-all-result"][data-id="sales"]')).toContain(
      fill(enCatalogue.apps.updateBlocked, { name: 'Sales', missing: 'loyalty' }),
    );
  });

  it('when every app failed, closing the result does not reload', async () => {
    updateModule.mockImplementation(async () => {
      throw failure('down');
    });
    const w = mountApps();
    await settle();
    await pressUpdateAll(w);
    await settle();
    expect(painted(w, '[data-testid="apps-update-all"]')).toContain(
      fill(enCatalogue.apps.updateAllSummary, { updated: 0, total: 2 }),
    );
    expect(painted(w, '[data-testid="apps-update-all-finish"]')).toBe(enCatalogue.apps.noticeClose);
    await w.find('[data-testid="apps-update-all-finish"]').trigger('click');
    await settle();
    expect(reloadForModuleUpdate).not.toHaveBeenCalled();
    expect(w.find('[data-testid="apps-update-all-result"]').exists()).toBe(false);
  });

  it('with some updated and some failed, the finish button reloads', async () => {
    updateModule
      .mockImplementationOnce(async () => {
        throw failure('down');
      })
      .mockImplementationOnce(async () => ok('inventory'));
    const w = mountApps();
    await settle();
    await pressUpdateAll(w);
    await settle();
    await w.find('[data-testid="apps-update-all-finish"]').trigger('click');
    await settle();
    expect(reloadForModuleUpdate).toHaveBeenCalledTimes(1);
  });

  it('nothing new after all (already up to date) does not reload', async () => {
    updateModule.mockImplementation(async (id: string) => ({ ...ok(id), updated: false }));
    const w = mountApps();
    await settle();
    await pressUpdateAll(w);
    await settle();
    expect(updateModule).toHaveBeenCalledTimes(2);
    expect(reloadForModuleUpdate).not.toHaveBeenCalled();
    // Nothing to report app by app: the result does not linger on screen.
    expect(w.find('[data-testid="apps-update-all-result"]').exists()).toBe(false);
  });

  it('a row «Update» pressed while the batch runs does not start a second update', async () => {
    const first = deferred<ReturnType<typeof ok>>();
    updateModule.mockImplementationOnce(() => first.promise);
    const w = mountApps();
    await settle();
    await pressUpdateAll(w);
    await settle();

    const table = w
      .findAll('ok-data-table')
      .map(
        (t) =>
          t.element as HTMLElement & {
            rows?: Array<Record<string, unknown>>;
            actions?: Array<{ id: string; disabled?: (row: Record<string, unknown>) => boolean }>;
          },
      )
      .find((t) => (t.rows ?? []).some((r) => r.id === 'inventory' && 'status' in r))!;
    const row = table.rows!.find((r) => r.id === 'inventory')!;
    // The queued app's own «Update» is greyed out while the batch owns the updates…
    const rowUpdate = table.actions!.find((a) => a.id === 'update')!;
    expect(rowUpdate.disabled?.(row)).toBe(true);
    // …and even a press that gets through starts nothing.
    table.dispatchEvent(new CustomEvent('rowAction', { detail: { actionId: 'update', row } }));
    await settle();
    expect(updateModule).toHaveBeenCalledTimes(1);
    expect(listModuleVersions).not.toHaveBeenCalled();

    // Once it is over, the row's own button works again.
    first.resolve(ok('sales'));
    updateModule.mockImplementationOnce(async () => ok('inventory'));
    await settle();
    const after = table.actions!.find((a) => a.id === 'update')!;
    expect(after.disabled?.(table.rows!.find((r) => r.id === 'inventory')!)).toBe(false);
  });
});

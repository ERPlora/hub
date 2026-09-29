// @vitest-environment happy-dom
// hub#1172 — the bell says «N apps have a new version» from any screen. The Apps screen is where
// the owner acts on it, so what that screen learns from `GET /api/modules/updates` replaces the
// notice at once: updating an app there must clear the bell without waiting hours for the next
// background check.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('vue-router', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
// `lib/icons` bakes its SVGs through `~icons/…?raw`, which this environment denies (same cut as
// apps-refresh-keeps-the-screen.test.ts).
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

function catalogueEntry(id: string) {
  return {
    id,
    name: id,
    description: 'what it does',
    priceLabel: '',
    priceAmount: null,
    priceInterval: null,
    isFree: true,
    moduleType: 'free',
    category: 'Operations',
    installed: true,
    available: true,
    version: '1.0.0',
    capabilities: [],
    minErploraVersion: null as string | null,
  };
}

let CATALOG: Array<Record<string, unknown>> = [];
let INSTALLED: Array<Record<string, unknown>> = [];
let UPDATES: Array<Record<string, unknown>> = [];

const cloudMarketplaceModules = vi.fn(async () => CATALOG);
const listModuleUpdates = vi.fn(async () => UPDATES);
const updateModule = vi.fn(async (..._args: unknown[]) => ({
  ok: true,
  module_id: 'sales',
  from: '1.0.0',
  to: '2.0.0',
  updated: true,
}));
const listInstalledModules = vi.fn(async () => INSTALLED);
let HUB_VERSION: string | null = 'v1.4.0';
vi.mock('../lib/system', () => ({
  fetchSystemInfo: async () => (HUB_VERSION ? { hubVersion: HUB_VERSION } : null),
}));

vi.mock('../lib/cloud', () => ({
  cloudMarketplaceModules: () => cloudMarketplaceModules(),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ on: () => () => {} }),
  requestInstall: vi.fn(),
  listInstalledModules: () => listInstalledModules(),
  activateModule: vi.fn(),
  deactivateModule: vi.fn(),
  uninstallModule: vi.fn(),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  InstallBlockedError: class InstallBlockedError extends Error {},
  ModuleActionError: class ModuleActionError extends Error {},
  updateModule: (...args: unknown[]) => updateModule(...args),
  listModuleUpdates: () => listModuleUpdates(),
  listModuleVersions: async (id: string) => ({ module_id: id, installed: '1.0.0', latest: null, versions: [] }),
  modulePublicationStatus: async () => null,
}));
const { moduleNav } = vi.hoisted(() => ({ moduleNav: { value: [] as Array<{ path: string }> } }));
vi.mock('../lib/nav', () => ({ moduleNav, refreshModuleNav: vi.fn() }));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/entitlement', () => ({
  isModuleEntitled: () => true,
  entitlementStatus: () => 'active',
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/setup-status', () => ({ setupStatus: ref(null), refreshSetupStatus: vi.fn() }));

import '@erplora/outfitkit/ok-data-table';
import AppsPage from './AppsPage.vue';
import { notificationCountOf, setNotificationCount } from '../lib/shell';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

type Row = Record<string, unknown>;
type Column = { key: string; render?: (row: Row) => Node | string };
type Action = { id: string; hidden?: (row: Row) => boolean };
type TableEl = HTMLElement & { rows?: Row[]; columns?: Column[]; actions?: Action[] };

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
  await flushPromises();
  await nextTick();
  await flushPromises();
  await nextTick();
}

/** «My apps»: the one whose rows are the runtime's installed modules. */
function mineTable(w: Wrapper): TableEl {
  const table = w
    .findAll('ok-data-table')
    .map((t) => t.element as TableEl)
    .find((t) => (t.rows ?? []).some((r) => r.id === 'sales' && 'status' in r));
  expect(table, 'the «My apps» table must list the app').toBeTruthy();
  return table!;
}
const mineRow = (w: Wrapper): Row => mineTable(w).rows!.find((r) => r.id === 'sales')!;

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});
beforeEach(() => {
  HUB_VERSION = 'v1.4.0';
  push.mockClear();
  updateModule.mockClear();
  listModuleUpdates.mockReset();
  listModuleUpdates.mockImplementation(async () => UPDATES);
  setNotificationCount(0, 'moduleUpdates');
  CATALOG = ['sales', 'kitchen', 'tables'].map((id) => ({ ...catalogueEntry(id), installed: true, version: '2.0.0' }));
  INSTALLED = ['sales', 'kitchen', 'tables'].map((id) => ({ id, name: id, version: '1.0.0', status: 'active' }));
  UPDATES = [
    {
      module_id: 'sales',
      installed: '1.0.0',
      latest: '2.0.0',
      update_available: true,
      pinned: null,
      latest_min_erplora_version: null,
    },
    // Needs a newer ERPlora: «My apps» offers no «Update» for it (hub#2082), so the bell does not count it.
    {
      module_id: 'kitchen',
      installed: '1.0.0',
      latest: '2.0.0',
      update_available: true,
      pinned: null,
      latest_min_erplora_version: '9.9.9',
    },
    {
      module_id: 'tables',
      installed: '1.0.0',
      latest: '1.0.0',
      update_available: false,
      pinned: null,
      latest_min_erplora_version: null,
    },
  ];
});

describe('the Apps screen feeds the «apps have a new version» notice (hub#1172)', () => {
  it('opening Apps publishes how many apps the owner can update', async () => {
    mountApps();
    await settle();
    expect(notificationCountOf('moduleUpdates')).toBe(1);
  });

  // «I don't know» is not «all up to date»: a failed fetch leaves the bell as it was.
  it('a failed fetch on the Apps screen keeps the bell as it was', async () => {
    setNotificationCount(3, 'moduleUpdates');
    listModuleUpdates.mockRejectedValue(new Error('offline'));
    mountApps();
    await settle();
    expect(notificationCountOf('moduleUpdates')).toBe(3);
  });

  // A screen that already knew the answer and then fails to re-check must not publish the empty list
  // its failure leaves behind: that would tell the owner «all up to date» while an app still waits.
  it('🔴 a re-check that fails after a good one keeps the bell as it was', async () => {
    UPDATES = UPDATES.map((u) => (u.module_id === 'tables' ? { ...u, latest: '2.0.0', update_available: true } : u));
    const w = mountApps();
    await settle();
    expect(notificationCountOf('moduleUpdates')).toBe(2);

    listModuleUpdates.mockRejectedValue(new Error('offline'));
    mineTable(w).dispatchEvent(new CustomEvent('rowAction', { detail: { actionId: 'update', row: mineRow(w) } }));
    await settle();

    expect(updateModule).toHaveBeenCalled();
    expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    expect(notificationCountOf('moduleUpdates')).toBe(2);
  });

  it('🔴 updating the app there clears the bell at once', async () => {
    const w = mountApps();
    await settle();
    expect(notificationCountOf('moduleUpdates')).toBe(1);

    UPDATES = UPDATES.map((u) => (u.module_id === 'sales' ? { ...u, installed: '2.0.0', update_available: false } : u));
    mineTable(w).dispatchEvent(new CustomEvent('rowAction', { detail: { actionId: 'update', row: mineRow(w) } }));
    await settle();

    expect(updateModule).toHaveBeenCalled();
    expect(notificationCountOf('moduleUpdates')).toBe(0);
  });
});

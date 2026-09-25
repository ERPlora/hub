// @vitest-environment happy-dom
// Regression test for ERPlora/hub#2054 — the card of an app that needs a newer hub offered «Install»
// and the owner only learnt the hub was too old AFTER pressing it (the runtime's refusal, hub#1620).
// The catalog row now carries the floor of the version it announces (saas#2239); the screen compares
// it with the version this hub runs and says it on the card, with no «Install» to press.
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
/** What the Cloud answers for one module's detail, per id. */

const cloudMarketplaceModules = vi.fn(async () => CATALOG);
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
  updateModule: vi.fn(),
  listModuleUpdates: async () => [],
  listModuleVersions: async () => [],
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

/** The catalog table: the one whose rows are the Cloud's catalogue. */
function catalogTable(w: Wrapper): TableEl {
  const table = w.findAll('ok-data-table').map((t) => t.element as TableEl)
    .find((t) => (t.rows ?? []).some((r) => r.id === 'sales'));
  expect(table, 'the catalogue table must list the app').toBeTruthy();
  return table!;
}
const row = (w: Wrapper): Row => catalogTable(w).rows!.find((r) => r.id === 'sales')!;
const visibleActions = (w: Wrapper): string[] =>
  (catalogTable(w).actions ?? []).filter((a) => !a.hidden?.(row(w))).map((a) => a.id);
function statusText(w: Wrapper): string {
  const column = (catalogTable(w).columns ?? []).find((c) => c.key === 'stateLabel');
  expect(column?.render, 'the status column renders the row state').toBeTypeOf('function');
  const painted = column!.render!(row(w));
  return typeof painted === 'string' ? painted : (painted as HTMLElement).textContent ?? '';
}

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
  await nextTick();
}

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});
beforeEach(() => {
  INSTALLED = [];
  HUB_VERSION = 'v1.4.0';
  push.mockClear();
  CATALOG = [{ ...catalogueEntry('sales'), installed: false, minErploraVersion: '9.9.9' }];
});

describe('an app whose announced version needs a newer hub (hub#2054)', () => {
  it('🔴 says so on the card and offers no «Install»', async () => {
    const w = mountApps();
    await settle();
    expect(row(w).state).toBe('needs_newer_hub');
    expect(visibleActions(w)).not.toContain('install');
    expect(visibleActions(w)).toEqual(['see_hub_updates']);
    expect(statusText(w)).toBe(enCatalogue.apps.stateNeedsNewerHub.replace('{version}', '9.9.9'));
  });

  it('says it in Spanish too', async () => {
    const w = mountApps('es');
    await settle();
    expect(statusText(w)).toBe(esCatalogue.apps.stateNeedsNewerHub.replace('{version}', '9.9.9'));
  });

  it('its action leads to the hub version and updates', async () => {
    const w = mountApps();
    await settle();
    catalogTable(w).dispatchEvent(new CustomEvent('rowAction', { detail: { actionId: 'see_hub_updates', row: row(w) } }));
    expect(push).toHaveBeenCalledWith('/system#updates');
  });

  it('keeps «Install» when the hub meets the floor, or when the floor cannot be checked', async () => {
    CATALOG = [{ ...catalogueEntry('sales'), installed: false, minErploraVersion: '1.4.0' }];
    let w = mountApps();
    await settle();
    expect(row(w).state).toBe('available');
    expect(visibleActions(w)).toEqual(['install']);

    // The hub version did not come back: the runtime still refuses at install time, the card does
    // not guess.
    CATALOG = [{ ...catalogueEntry('sales'), installed: false, minErploraVersion: '9.9.9' }];
    HUB_VERSION = null;
    w = mountApps();
    await settle();
    expect(row(w).state).toBe('available');
  });
});

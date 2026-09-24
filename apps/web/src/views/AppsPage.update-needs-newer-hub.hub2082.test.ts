// @vitest-environment happy-dom
// Regression test for ERPlora/hub#2082 — an INSTALLED app whose new version needs a newer ERPlora
// still offered «Update», and the owner only learnt the hub was too old when the runtime refused it.
// `GET /api/modules/updates` now carries the floor of the version it offers
// (`latest_min_erplora_version`); both the catalog card and «My apps» compare it with the version
// this hub runs (`hubTooOldFor`, hub#2054) and say it instead of offering an update that would fail.
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
  listModuleUpdates: async () => UPDATES,
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
    .find((t) => (t.rows ?? []).some((r) => r.id === 'sales' && 'stateLabel' in r));
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

/** «My apps»: the one whose rows are the runtime's installed modules. */
function mineTable(w: Wrapper): TableEl {
  const table = w.findAll('ok-data-table').map((t) => t.element as TableEl)
    .find((t) => (t.rows ?? []).some((r) => r.id === 'sales' && 'status' in r));
  expect(table, 'the «My apps» table must list the app').toBeTruthy();
  return table!;
}
const mineRow = (w: Wrapper): Row => mineTable(w).rows!.find((r) => r.id === 'sales')!;
const mineVisibleActions = (w: Wrapper): string[] =>
  (mineTable(w).actions ?? []).filter((a) => !a.hidden?.(mineRow(w))).map((a) => a.id);
function mineVersionText(w: Wrapper): string {
  const column = (mineTable(w).columns ?? []).find((c) => c.key === 'version') as
    | (Column & { format?: (row: Row) => string })
    | undefined;
  expect(column?.format, 'the version column formats the row').toBeTypeOf('function');
  return column!.format!(mineRow(w));
}

const blockedLabel = (catalogue: { apps: { stateUpdateNeedsNewerHub: string } }) =>
  catalogue.apps.stateUpdateNeedsNewerHub.replace('{version}', '2.0.0').replace('{floor}', '9.9.9');

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});
beforeEach(() => {
  HUB_VERSION = 'v1.4.0';
  push.mockClear();
  CATALOG = [{ ...catalogueEntry('sales'), installed: true, version: '2.0.0' }];
  INSTALLED = [{ id: 'sales', name: 'Sales', version: '1.0.0', status: 'active' }];
  UPDATES = [{
    module_id: 'sales', installed: '1.0.0', latest: '2.0.0', update_available: true, pinned: null,
    latest_min_erplora_version: '9.9.9',
  }];
});

describe('an installed app whose next version needs a newer ERPlora (hub#2082)', () => {
  it('🔴 the catalog card names the version and its floor, with no «Update»', async () => {
    const w = mountApps();
    await settle();
    expect(row(w).state).toBe('needs_newer_hub');
    expect(visibleActions(w)).toEqual(['see_hub_updates']);
    expect(statusText(w)).toBe(blockedLabel(enCatalogue));
  });

  it('says it in Spanish too', async () => {
    const w = mountApps('es');
    await settle();
    expect(statusText(w)).toBe(blockedLabel(esCatalogue));
  });

  it('🔴 «My apps» offers no «Update» either, and leads to the ERPlora updates', async () => {
    const w = mountApps();
    await settle();
    expect(mineVisibleActions(w)).not.toContain('update');
    expect(mineVisibleActions(w)).toContain('see_hub_updates');
    expect(mineVersionText(w)).toContain(blockedLabel(enCatalogue));
    mineTable(w).dispatchEvent(new CustomEvent('rowAction', { detail: { actionId: 'see_hub_updates', row: mineRow(w) } }));
    expect(push).toHaveBeenCalledWith('/system#updates');
  });

  it('keeps «Update» when the hub meets the floor', async () => {
    UPDATES = [{ ...UPDATES[0], latest_min_erplora_version: '1.4.0' }];
    const w = mountApps();
    await settle();
    expect(row(w).state).toBe('updatable');
    expect(visibleActions(w)).toEqual(['update']);
    expect(mineVisibleActions(w)).toContain('update');
    expect(mineVisibleActions(w)).not.toContain('see_hub_updates');
    expect(mineVersionText(w)).toBe('1.0.0 → 2.0.0');
  });

  it('keeps «Update» when the floor cannot be checked (no floor, or no hub version)', async () => {
    UPDATES = [{ ...UPDATES[0], latest_min_erplora_version: null }];
    let w = mountApps();
    await settle();
    expect(row(w).state).toBe('updatable');

    // A runtime older than the field omits it; the hub version did not come back: nothing is
    // guessed — the runtime still refuses at update time.
    const { latest_min_erplora_version: _omitted, ...older } = UPDATES[0];
    UPDATES = [{ ...older }];
    w = mountApps();
    await settle();
    expect(row(w).state).toBe('updatable');

    UPDATES = [{ ...older, latest_min_erplora_version: '9.9.9' }];
    HUB_VERSION = null;
    w = mountApps();
    await settle();
    expect(row(w).state).toBe('updatable');
    expect(mineVisibleActions(w)).toContain('update');
  });
});

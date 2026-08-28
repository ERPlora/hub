// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1134 — a RETIRED module looks exactly like a healthy one in
// «My apps».
//
// 🔴 The failure mode is the one ADR-0380 takes from WordPress.org's *closed plugin*: the plugin
// is closed, the site keeps it (on purpose — that is the half that does not break the fleet), and
// the core paints it AS IF IT WERE UP TO DATE, because there is no update to offer. Nobody ever
// finds out. `online_booking`, `cart_checkout`, `payments` and `invoice_series` are retired in
// production today, so every hub that has one of them is that case.
//
// ⚠️ Where the status comes from, verified against `ERPlora/saas@origin/develop`: the catalogue the
// hub reads (`GET /api/v1/marketplace/modules/`) filters `publication_status='listed'` in its
// `list` action (`ModuleViewSet.get_queryset`) — so a retired module is NOT in it and cannot be
// painted from it. The door that does answer for it is the DETAIL one, `retrieve`, which draws
// from the unfiltered base queryset and is in `MACHINE_OK_ACTIONS`, so the runtime can ask it with
// the hub's machine token. Hence: what the catalogue listed is `listed` by construction, and the
// only ids worth one detail call are the installed ones the catalogue did NOT list. A healthy hub
// therefore makes ZERO extra calls — which is what keeps this off the `window.focus` refresh path.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
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
  };
}

let CATALOG: Array<Record<string, unknown>> = [];
let INSTALLED: Array<Record<string, unknown>> = [];
/** What the Cloud answers for one module's detail, per id. */
let PUBLICATION: Record<string, 'listed' | 'unlisted' | 'retired'> = {};
/** Ids the screen actually asked the Cloud about — the cost this design must not pay twice. */
const asked: string[] = [];
let publicationFails = false;

const cloudMarketplaceModules = vi.fn(async () => CATALOG);
const listInstalledModules = vi.fn(async () => INSTALLED);
const modulePublicationStatus = vi.fn(async (id: string) => {
  asked.push(id);
  if (publicationFails) throw new Error('cloud down');
  return PUBLICATION[id] ?? null;
});

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
  modulePublicationStatus: (id: string) => modulePublicationStatus(id),
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
import { publicationStatusOf, modulesWithUnknownPublication } from '../lib/apps-catalog';

type Row = Record<string, unknown>;
type Column = { key: string; render?: (row: Row) => Node | string };
type TableEl = HTMLElement & { rows?: Row[]; columns?: Column[] };

const mounted: Array<{ unmount: () => void }> = [];

function mountApps(locale: 'en' | 'es' = 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(AppsPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
  mounted.push(wrapper);
  return wrapper;
}

type Wrapper = ReturnType<typeof mountApps>;

const mineTable = (w: Wrapper): TableEl =>
  w.findAll('ok-data-table').map((t) => t.element as TableEl)[0];

/** The text the name cell paints for one row — name plus whatever chip hangs off it. */
function nameCellText(w: Wrapper, row: Row): string {
  const column = (mineTable(w).columns ?? []).find((c) => c.key === 'name');
  expect(column?.render, 'the module name cell must render, so it can carry the chip').toBeTypeOf(
    'function',
  );
  const painted = column!.render!(row);
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
  CATALOG = [];
  INSTALLED = [];
  PUBLICATION = {};
  asked.length = 0;
  publicationFails = false;
  moduleNav.value = [];
  cloudMarketplaceModules.mockClear();
  listInstalledModules.mockClear();
  modulePublicationStatus.mockClear();
});

describe('the publication status the SaaS already knows (hub#1134)', () => {
  it('normalises what the Cloud sends, and treats anything it does not know as "listed"', () => {
    expect(publicationStatusOf('retired')).toBe('retired');
    expect(publicationStatusOf('unlisted')).toBe('unlisted');
    expect(publicationStatusOf('listed')).toBe('listed');
    // A SaaS older than saas#1542 does not send the field at all. Absent is not "retired": the
    // only safe reading of silence is the state that changes nothing on screen.
    expect(publicationStatusOf(undefined)).toBe('listed');
    expect(publicationStatusOf(null)).toBe('listed');
    expect(publicationStatusOf('sunset')).toBe('listed');
  });

  it('only wants a lookup for what the catalogue did NOT list', () => {
    const installed = ['invoice', 'online_booking'];
    const listed = new Set(['invoice', 'customers']);
    expect(modulesWithUnknownPublication(installed, listed, new Map())).toEqual(['online_booking']);
    // Already answered once: asking again on every refresh is what would put this on the
    // `window.focus` path.
    expect(
      modulesWithUnknownPublication(
        installed,
        listed,
        new Map([['online_booking', 'retired' as const]]),
      ),
    ).toEqual([]);
  });

  it('🔴 marks an installed module the marketplace has RETIRED, in its row', async () => {
    INSTALLED = [
      { id: 'online_booking', name: 'Online booking', version: '1.0.0', status: 'active' },
    ];
    PUBLICATION = { online_booking: 'retired' };
    const wrapper = mountApps();
    await settle();

    const row = (mineTable(wrapper).rows ?? [])[0];
    expect(row?.publicationStatus, 'the row must carry the status the SaaS sent').toBe('retired');
  });

  it('🔴 paints the chip next to the app name, in the reader’s language', async () => {
    INSTALLED = [
      { id: 'online_booking', name: 'Online booking', version: '1.0.0', status: 'active' },
    ];
    PUBLICATION = { online_booking: 'retired' };

    const english = mountApps('en');
    await settle();
    const englishRow = (mineTable(english).rows ?? [])[0]!;
    expect(nameCellText(english, englishRow)).toContain('Online booking');
    expect(nameCellText(english, englishRow)).toContain(enCatalogue.apps.publicationRetired);

    const spanish = mountApps('es');
    await settle();
    const spanishRow = (mineTable(spanish).rows ?? [])[0]!;
    expect(nameCellText(spanish, spanishRow)).toContain(esCatalogue.apps.publicationRetired);
    // The binding rule of 2026-08-04: English is the source and Spanish is NOT optional, and the
    // two must not be the same string by accident.
    expect(esCatalogue.apps.publicationRetired).not.toBe(enCatalogue.apps.publicationRetired);
  });

  it('🔴 says what «retired» MEANS — it keeps working, it is just not offered any more', async () => {
    INSTALLED = [
      { id: 'online_booking', name: 'Online booking', version: '1.0.0', status: 'active' },
    ];
    PUBLICATION = { online_booking: 'retired' };
    const wrapper = mountApps();
    await settle();

    const notice = wrapper.find('[data-test="apps-retired-notice"]');
    expect(notice.exists(), 'a chip alone does not explain anything').toBe(true);
    expect(notice.text()).toContain('Online booking');
  });

  it('leaves a healthy app alone — no chip, no notice, and NO extra call to the Cloud', async () => {
    CATALOG = [catalogueEntry('invoice')];
    INSTALLED = [{ id: 'invoice', name: 'Invoice', version: '1.0.0', status: 'active' }];
    const wrapper = mountApps();
    await settle();

    const row = (mineTable(wrapper).rows ?? [])[0]!;
    expect(row.publicationStatus).toBe('listed');
    expect(nameCellText(wrapper, row)).not.toContain(enCatalogue.apps.publicationRetired);
    expect(wrapper.find('[data-test="apps-retired-notice"]').exists()).toBe(false);
    expect(asked, 'the catalogue already answered for it — asking again is pure cost').toEqual([]);
  });

  it('an UNLISTED module carries no chip: it still installs by direct reference (ADR-0380)', async () => {
    INSTALLED = [{ id: 'tobacco', name: 'Tobacco', version: '1.0.0', status: 'active' }];
    PUBLICATION = { tobacco: 'unlisted' };
    const wrapper = mountApps();
    await settle();

    const row = (mineTable(wrapper).rows ?? [])[0]!;
    expect(row.publicationStatus).toBe('unlisted');
    expect(nameCellText(wrapper, row)).not.toContain(enCatalogue.apps.publicationRetired);
    expect(wrapper.find('[data-test="apps-retired-notice"]').exists()).toBe(false);
  });

  it('a Cloud that does not answer says NOTHING — silence is never painted as a verdict', async () => {
    INSTALLED = [
      { id: 'online_booking', name: 'Online booking', version: '1.0.0', status: 'active' },
    ];
    publicationFails = true;
    const wrapper = mountApps();
    await settle();

    const row = (mineTable(wrapper).rows ?? [])[0]!;
    expect(row.publicationStatus).toBeNull();
    expect(nameCellText(wrapper, row)).not.toContain(enCatalogue.apps.publicationRetired);
    expect(wrapper.find('[data-test="apps-retired-notice"]').exists()).toBe(false);
  });

  it('does not go asking when the CATALOGUE itself failed — everything would look retired', async () => {
    INSTALLED = [{ id: 'invoice', name: 'Invoice', version: '1.0.0', status: 'active' }];
    cloudMarketplaceModules.mockImplementationOnce(async () => {
      throw new Error('cloud down');
    });
    const wrapper = mountApps();
    await settle();

    expect(asked, 'a catalogue that did not answer lists nothing: that is not "retired"').toEqual(
      [],
    );
    expect(wrapper.find('[data-test="apps-retired-notice"]').exists()).toBe(false);
  });
});

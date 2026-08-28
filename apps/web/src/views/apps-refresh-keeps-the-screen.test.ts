// @vitest-environment happy-dom
// hub#1129 + hub#1122 — «Añadir apps» no pinta nada, y «Mis apps» dice que no hay apps.
//
// 🔴 The hole this closes: `loadCatalog()` raises a PAGE-WIDE `loading` flag, and the template
// hides the WHOLE content behind it (`v-if="loading"`). So every refresh of the catalogue DESTROYS
// both tables — the installed list, the search box, the banners — and puts a spinner in their
// place. And the catalogue refreshes far more often than anyone reading the screen would guess:
//
//   • on `window.focus` (`recheckEntitlement`, wired for the whole life of the view),
//   • on every language change,
//   • after every install or update.
//
// Measured on the production hub `qa-pm149-…` (shell v1.1.9, 2026-08-25): ONE synthetic
// `window.dispatchEvent(new Event('focus'))` took the screen from «2 tables, no spinner» to
// «0 tables, spinner» and kept it there for ~3 s. Alt-tabbing back into the till, dismissing a
// system dialog, or an automated QA pass that refocuses the page on every step, all land inside
// that window — which is exactly what both reports describe from two different angles: the
// catalogue that «never paints» (hub#1129) and «My apps» that says there are none while the
// runtime has one (hub#1122). Neither is about merging the catalogue with the installed list.
//
// The rule is the one `list-load-state.ts` already writes down for the installed list: DATA WINS.
// What is on screen stays on screen while it reloads, and the three sentences — loading, empty,
// failed — are never said one for another. This file holds the catalogue to the same contract.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

const routerPush = vi.fn();
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: (...a: unknown[]) => routerPush(...a), replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
// `lib/icons` bakes its SVGs through `~icons/…?raw`, which this environment denies. `shallow`
// stubs children at RENDER time but still IMPORTS them, so AppPage → AppTopbar → lib/icons runs
// regardless of stubbing (same cut as dashboard-widget-board.test.ts).
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const CATALOG = Array.from({ length: 25 }, (_, i) => ({
  id: `mod${i}`,
  name: `Module ${i}`,
  description: 'what it does',
  priceLabel: '',
  priceAmount: null,
  priceInterval: null,
  isFree: true,
  moduleType: 'free',
  category: 'Operations',
  installed: false,
  available: true,
  version: '1.0.0',
  capabilities: [],
}));

/** The catalogue call, under the test's control: each call takes the next queued answer. */
const catalogAnswers: Array<() => Promise<unknown>> = [];
const cloudMarketplaceModules = vi.fn(() => {
  const next = catalogAnswers.shift() ?? (() => Promise.resolve(CATALOG));
  return next();
});
const listInstalledModules = vi.fn(async () => INSTALLED);
let INSTALLED: Array<Record<string, unknown>> = [];

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
  // hub#1134: la pantalla pregunta por el estado de publicación de lo instalado que el catálogo no
  // lista. Aquí no hay ninguno en ese caso, y `null` es «no lo sé» — que es lo que no pinta nada.
  modulePublicationStatus: async () => null,
}));
// `vi.hoisted`: the `vi.mock` factory is lifted above every `const` in this file, so a ref the
// factory RETURNS (rather than closes over lazily) has to be created up there with it.
const { moduleNav } = vi.hoisted(() => ({ moduleNav: { value: [] as Array<{ path: string }> } }));
vi.mock('../lib/nav', () => ({ moduleNav, refreshModuleNav: vi.fn() }));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/entitlement', () => ({
  isModuleEntitled: () => true,
  entitlementStatus: () => 'active',
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/setup-status', () => ({ setupStatus: ref(null), refreshSetupStatus: vi.fn() }));

// The REAL Web Component: `rows`/`columns` travel by PROPERTY (`attribute: false` in OutfitKit),
// and Vue only sets a property on a custom element it can see — with the element undefined the
// binding silently degrades to an attribute and every assertion below would read `undefined`.
import '@erplora/outfitkit/ok-data-table';
import AppsPage from './AppsPage.vue';
// REAL catalogues: English is the source language and Spanish is NOT optional (binding rule of
// 2026-08-04).
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

type TableEl = HTMLElement & { rows?: unknown[] };

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
  return { wrapper, i18n };
}

type Wrapper = ReturnType<typeof mountApps>['wrapper'];

const tablesOf = (w: Wrapper): TableEl[] =>
  w.findAll('ok-data-table').map((t) => t.element as TableEl);

/** The catalogue table is the second one; both live behind `v-show`, so both are always found. */
const catalogTable = (w: Wrapper): TableEl | undefined => tablesOf(w)[1];
const mineTable = (w: Wrapper): TableEl | undefined => tablesOf(w)[0];

/** Opens the «Add apps» tab, the one both reports are about. */
async function showCatalogTab(w: Wrapper): Promise<void> {
  (w.vm as unknown as { tab: 'mine' | 'all' | 'paid' }).tab = 'all';
  await nextTick();
}

/** A refresh that is STILL IN FLIGHT — the state the screen must survive without going blank. */
function queuePendingCatalogAnswer(): void {
  catalogAnswers.push(() => new Promise(() => {}));
}

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
}

// Every mounted view keeps a `window.focus` listener alive for as long as it lives, so a wrapper
// left behind would answer the NEXT test's focus event and eat its queued answer.
afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

beforeEach(() => {
  catalogAnswers.length = 0;
  INSTALLED = [];
  moduleNav.value = [];
  routerPush.mockClear();
  cloudMarketplaceModules.mockClear();
  listInstalledModules.mockClear();
});

describe('a refresh of the catalogue does not blank the screen (hub#1129)', () => {
  it('paints the catalogue of a hub with ZERO installed apps', async () => {
    const { wrapper } = mountApps();
    await settle();

    expect(catalogTable(wrapper)?.rows).toHaveLength(25);
    expect(mineTable(wrapper)?.rows).toHaveLength(0);
  });

  it('🔴 keeps both tables on screen while a refresh triggered by window focus is in flight', async () => {
    const { wrapper } = mountApps();
    await settle();
    expect(tablesOf(wrapper)).toHaveLength(2);

    queuePendingCatalogAnswer();
    window.dispatchEvent(new Event('focus'));
    await settle();

    // This is the whole defect: today the page-wide `loading` flag tears the content down and the
    // person looking at «Add apps» sees an empty area for as long as the Cloud takes to answer.
    expect(tablesOf(wrapper), 'the tables were destroyed by a refresh').toHaveLength(2);
  });

  it('🔴 keeps the 25 catalogue rows while the refresh is in flight — data wins', async () => {
    const { wrapper } = mountApps();
    await settle();

    queuePendingCatalogAnswer();
    window.dispatchEvent(new Event('focus'));
    await settle();

    expect(catalogTable(wrapper)?.rows).toHaveLength(25);
  });

  // hub#1122 is the same tear-down seen from the other tab: «My apps» reported «no apps
  // installed» while the runtime had one, because during the catalogue refresh the installed
  // table did not exist at all.
  it('🔴 keeps «My apps» listing its installed apps while the CATALOGUE refreshes (hub#1122)', async () => {
    INSTALLED = [{ id: 'customers', name: 'Customers', version: '2.3.16', status: 'active' }];
    const { wrapper } = mountApps();
    await settle();
    expect(mineTable(wrapper)?.rows).toHaveLength(1);

    queuePendingCatalogAnswer();
    window.dispatchEvent(new Event('focus'));
    await settle();

    expect(mineTable(wrapper)?.rows, '«My apps» lost its list to a catalogue refresh').toHaveLength(1);
  });

  it('🔴 does not throw the catalogue away when a refresh FAILS — the failure is said, not shown instead', async () => {
    const { wrapper } = mountApps();
    await settle();
    await showCatalogTab(wrapper);

    catalogAnswers.push(() => Promise.reject(new Error('cloud down')));
    window.dispatchEvent(new Event('focus'));
    await settle();

    expect(catalogTable(wrapper)?.rows, 'a transient failure emptied the catalogue').toHaveLength(25);
    // And it is SAID, next to the list (the banner the screen already has).
    expect(wrapper.find('ok-inline-feedback[tone="danger"]').text()).toContain(
      enCatalogue.apps.catalogLoadError,
    );
  });
});

describe('the catalogue says which of the three it is (hub#1129)', () => {
  it('🔴 says it is LOADING, not «nothing matches your search», while it has no answer yet', async () => {
    queuePendingCatalogAnswer();
    const { wrapper } = mountApps();
    await settle();
    await showCatalogTab(wrapper);

    const table = catalogTable(wrapper);
    expect(table, 'the catalogue table must be on screen while it loads').toBeTruthy();
    expect(table?.getAttribute('empty-message')).toBe(enCatalogue.apps.loadingCatalog);
  });

  it('🔴 says it FAILED, not «nothing matches your search», when the first answer never came', async () => {
    catalogAnswers.push(() => Promise.reject(new Error('cloud down')));
    const { wrapper } = mountApps();
    await settle();
    await showCatalogTab(wrapper);

    expect(catalogTable(wrapper)?.getAttribute('empty-message')).toBe(
      enCatalogue.apps.catalogLoadError,
    );
  });

  it('says «nothing matches» only about an answer that came back empty', async () => {
    catalogAnswers.push(async () => []);
    const { wrapper } = mountApps();
    await settle();
    await showCatalogTab(wrapper);

    expect(catalogTable(wrapper)?.getAttribute('empty-message')).toBe(enCatalogue.apps.emptyCatalog);
  });

  it('says all three in Spanish too — English is the source, Spanish is not optional', async () => {
    queuePendingCatalogAnswer();
    const { wrapper } = mountApps('es');
    await settle();
    await showCatalogTab(wrapper);

    expect(catalogTable(wrapper)?.getAttribute('empty-message')).toBe(esCatalogue.apps.loadingCatalog);
    expect(esCatalogue.apps.loadingCatalog).not.toBe(enCatalogue.apps.loadingCatalog);
  });
});

// The buttons on every card live INSIDE the tables' shadow DOM and reach this screen as a single
// `rowAction` event, wired imperatively (`wireTable`) because the event name is camelCase. That
// wiring used to hang off the page-wide `loading` flag — the one hub#1129 removed. It now watches
// the ELEMENT, and this is the guard that the swap kept the buttons alive: a wiring that silently
// stops listening turns every card action inert without a single error (the demo bug of 2026-07-12).
describe('the row actions stay wired after the loading flag is gone (hub#1129)', () => {
  const rowAction = (el: TableEl, detail: Record<string, unknown>): void => {
    el.dispatchEvent(new CustomEvent('rowAction', { detail }));
  };

  it('a press on «Open» still navigates to the app', async () => {
    INSTALLED = [{ id: 'customers', name: 'Customers', version: '2.3.16', status: 'active' }];
    moduleNav.value = [{ path: '/m/customers' }];
    const { wrapper } = mountApps();
    await settle();

    rowAction(mineTable(wrapper)!, {
      actionId: 'open',
      row: { id: 'customers', name: 'Customers', status: 'active' },
    });

    expect(routerPush).toHaveBeenCalledWith('/m/customers');
  });

  it('and it is still wired after a refresh that would once have replaced the element', async () => {
    INSTALLED = [{ id: 'customers', name: 'Customers', version: '2.3.16', status: 'active' }];
    moduleNav.value = [{ path: '/m/customers' }];
    const { wrapper } = mountApps();
    await settle();

    window.dispatchEvent(new Event('focus'));
    await settle();

    rowAction(mineTable(wrapper)!, {
      actionId: 'open',
      row: { id: 'customers', name: 'Customers', status: 'active' },
    });

    expect(routerPush).toHaveBeenCalledWith('/m/customers');
  });
});

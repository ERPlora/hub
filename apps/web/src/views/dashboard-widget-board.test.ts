// @vitest-environment happy-dom
// hub#768 — «Dashboard: personalización sin widgets y textos en inglés en la interfaz española».
//
// 🔴 The hole this closes: the two halves of the report are ONE defect. The Summary tab is a
// `v-if` (`DashboardPage.vue`), so leaving for Activity DESTROYS the `<ok-widget-board>` and coming
// back mounts a BRAND NEW element. Everything the board knows travels by PROPERTY —`widgets`,
// `presets`, `labels` (`attribute: false` in OutfitKit)— and properties do not survive the element
// that held them. The replacement therefore comes back with an empty catalogue AND with
// OutfitKit's built-in English defaults. Empty customisation and English text in a Spanish UI are
// the same missing re-apply, not two bugs.
//
// The strings were never missing: `i18n/locales/es.ts` has translated them since 2026-06-23, and
// OutfitKit hardcodes English BY CONTRACT (`DEFAULT_LABELS`, overridden via `.labels`). So the fix
// belongs in the shell — pass them, and pass them AGAIN whenever the element or the locale changes.
// The sibling `ok-data-table` in this very file already does exactly that (`watch(activityTable)` +
// `watch(locale)`); the board simply never got the same treatment.
//
// These tests mount the real view and inspect the real element, rather than grepping the source
// like the older dashboard tests: the defect is the WIRING, and a source match would pass on code
// that still hands a dead element its labels.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref, type Ref } from 'vue';

// ── Doubles for everything the view reaches for; none of it is what is under test ──────────────
const queryPage = vi.fn(async (..._args: unknown[]) => ({
  rows: [],
  total: 0,
  limit: 100,
  offset: 0,
}));
const collectDashboardWidgets = vi.fn();

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
vi.mock('../lib/runtime', () => ({
  getClient: () => ({ queryPage: (...a: unknown[]) => queryPage(...a) }),
  getHubSector: () => 'hosteleria',
  listInstalledModules: async () => [],
}));
vi.mock('../lib/dashboard-widgets', () => ({
  collectDashboardWidgets: (...a: unknown[]) => collectDashboardWidgets(...a),
}));
vi.mock('../lib/dashboard-blueprint-widget', () => ({ buildBlueprintWidget: vi.fn() }));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]), moduleNavState: ref('ready') }));
// The real module, except for the read: `setupStatus` becomes a ref each test can answer (hub#2199),
// and the constants the panel's rules read (`STATE_DONE`…) stay the real ones.
vi.mock('../lib/setup-status', async (importOriginal) => {
  const { ref: vueRef } = await import('vue');
  return {
    ...(await importOriginal<typeof import('../lib/setup-status')>()),
    refreshSetupStatus: vi.fn(),
    setupStatus: vueRef(null),
  };
});
vi.mock('../lib/shell', () => ({ openAssistantForSetup: vi.fn() }));
vi.mock('../lib/bridge-transport', () => ({ detectPeripherals: async () => null }));
vi.mock('../lib/system-health', () => ({
  printerLine: () => null,
  probeFromCoverage: () => null,
  whatsappLine: () => null,
  isWhatsAppInstalled: () => false,
}));
vi.mock('../lib/dashboard-heading', () => ({
  GREETING_KEY: { morning: 'dashboard.morning' },
  panelHeading: () => ({ kind: 'business', name: 'Bar Manolo SL' }),
}));
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({ business_legal_name: 'Bar Manolo SL', country_code: 'ES', language: 'es' }),
  // hub#1212: the dashboard formats its dates through `lib/format-datetime`, which asks this module
  // for the business timezone. `null` = the boot has not seeded it, so the helper falls back to the
  // machine zone — which is what this board test wants: it asserts labels, not clocks.
  publishedHubTimezone: () => null,
}));
vi.mock('../lib/money', () => ({ formatAmount: (n: number) => String(n) }));
vi.mock('../lib/data-table-labels', () => ({ dataTableLabels: () => ({}) }));
vi.mock('../components/HubIcon.vue', () => ({
  default: { name: 'HubIcon', template: '<span />' },
}));
// `lib/icons` bakes its SVGs through `~icons/…?raw`, which this environment denies. `shallow`
// stubs children at RENDER time but still IMPORTS them, so the chain AppPage → AppTopbar →
// lib/icons runs regardless of stubbing. Cutting it here is one mock instead of one per component.
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));

import DashboardPage from './DashboardPage.vue';
import { refreshSetupStatus, setupStatus as mockedSetupStatus, type SetupStatus } from '../lib/setup-status';

/** The mocked read, writable: the view only ever sees it as a read-only computed. */
const setupStatusRef = mockedSetupStatus as unknown as Ref<SetupStatus | null>;

/** A `hub.setup.status` document whose only item is `apps` in the given state. */
function statusWithApps(state: 'done' | 'pending'): SetupStatus {
  return {
    items: [
      {
        key: 'apps',
        source: 'core',
        moduleId: null,
        state,
        required: true,
        level: 'functional',
        title: 'Your apps',
        description: '',
        icon: 'grid-outline',
        route: '/apps',
        order: 10,
        actions: ['template', 'catalog'],
        actionable: true,
        origin: 'user',
        missingCapabilities: [],
      },
    ],
    total: 1,
    pending: state === 'pending' ? 1 : 0,
    unavailable: 0,
    blockingPending: 0,
    done: state === 'done' ? 1 : 0,
  };
}

// Only the keys this contract reads. Real Spanish, so a leaked English default is unmistakable.
const messages = {
  en: {
    dashboard: {
      customizePanel: 'Customize panel',
      closePanel: 'Close',
      presetsTitle: 'Start from a preset',
      activeWidgets: 'Active · drag to reorder',
      availableWidgets: 'Available',
      emptyPanel: 'Empty panel. Tap ⋮ to add widgets.',
      blueprintTitle: 'Data',
      recommendedPreset: 'Recommended',
    },
  },
  es: {
    dashboard: {
      customizePanel: 'Personalizar panel',
      closePanel: 'Cerrar',
      presetsTitle: 'Empezar desde un preset',
      activeWidgets: 'Activos · arrastra para reordenar',
      availableWidgets: 'Disponibles',
      emptyPanel: 'Panel vacío. Pulsa ⋮ para añadir widgets.',
      blueprintTitle: 'Datos',
      recommendedPreset: 'Recomendado',
    },
  },
};

type BoardEl = HTMLElement & {
  widgets?: { id: string }[];
  presets?: { id: string; widgets: string[] }[];
  labels?: Record<string, string>;
  value?: string[];
};

/**
 * What a board that has never been customised paints, given what the shell handed it.
 *
 * Mirrors the documented start of `ok-widget-board` (OutfitKit, `willUpdate`), minus the saved
 * layout: a non-empty `value` wins — filtered to the ids the catalogue knows, exactly like its
 * `active` getter — and an EMPTY one is read as «not given», falling to the first preset and then to
 * the WHOLE catalogue. That last fallback is the one hub#1100 must never reach.
 */
function whatTheBoardShows(board: BoardEl): string[] {
  const ids = (board.widgets ?? []).map((w) => w.id);
  const known = new Set(ids);
  const value = board.value ?? [];
  if (value.length) return value.filter((id) => known.has(id));
  if (board.presets?.length) return board.presets[0].widgets.filter((id) => known.has(id));
  return ids;
}
type Vm = { tab: 'resumen' | 'actividad' };

function mountDashboard(locale = 'es') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages,
  });
  const wrapper = mount(DashboardPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
  return { wrapper, i18n };
}

function boardOf(wrapper: ReturnType<typeof mountDashboard>['wrapper']): BoardEl {
  const el = wrapper.find('ok-widget-board');
  expect(el.exists(), 'the board is not on screen').toBe(true);
  return el.element as BoardEl;
}

/** Leaves Summary for Activity and comes back — the round trip a user makes with the tab bar. */
async function roundTripThroughActivity(wrapper: ReturnType<typeof mountDashboard>['wrapper']) {
  const vm = wrapper.vm as unknown as Vm;
  vm.tab = 'actividad';
  await nextTick();
  expect(wrapper.find('ok-widget-board').exists(), 'the board should be GONE (v-if)').toBe(false);
  vm.tab = 'resumen';
  await nextTick();
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  setupStatusRef.value = null;
  // The whole shape `collectDashboardWidgets` returns. It used to omit `defaultActive`, and the old
  // spread of it threw inside the view's `try`, so these tests ran on the degraded core-only board.
  collectDashboardWidgets.mockResolvedValue({
    widgets: [{ id: 'sales.today', title: 'Ventas de hoy', size: 'sm', render: () => {} }],
    presets: [{ id: 'recommended', label: 'Recomendado', widgets: ['sales.today'] }],
    defaultActive: ['sales.today'],
  });
});

describe('the widget board survives leaving the tab and coming back (hub#768)', () => {
  it('has its catalogue on first paint', async () => {
    const { wrapper } = mountDashboard();
    await flushPromises();
    expect(boardOf(wrapper).widgets?.length ?? 0).toBeGreaterThan(0);
  });

  it('is a NEW element after the round trip — the v-if really destroys it', async () => {
    const { wrapper } = mountDashboard();
    await flushPromises();
    const before = boardOf(wrapper);
    await roundTripThroughActivity(wrapper);
    expect(boardOf(wrapper)).not.toBe(before);
  });

  it('🔴 comes back WITH its widgets, not as an empty panel', async () => {
    const { wrapper } = mountDashboard();
    await flushPromises();
    await roundTripThroughActivity(wrapper);
    // The half of the report that reads «customisation without widgets».
    expect(boardOf(wrapper).widgets?.length ?? 0).toBeGreaterThan(0);
  });

  it('🔴 comes back with its presets too, or the picker offers nothing to start from', async () => {
    const { wrapper } = mountDashboard();
    await flushPromises();
    await roundTripThroughActivity(wrapper);
    expect(boardOf(wrapper).presets?.length ?? 0).toBeGreaterThan(0);
  });

  it('🔴 comes back in SPANISH, not in OutfitKit English defaults', async () => {
    const { wrapper } = mountDashboard('es');
    await flushPromises();
    await roundTripThroughActivity(wrapper);
    // The other half: «English text in the Spanish interface». Same missing re-apply.
    expect(boardOf(wrapper).labels?.customize).toBe('Personalizar panel');
  });
});

describe('the board follows the language the user picks (hub#768)', () => {
  it('is labelled in the active language on first paint', async () => {
    const { wrapper } = mountDashboard('es');
    await flushPromises();
    expect(boardOf(wrapper).labels?.customize).toBe('Personalizar panel');
  });

  it('🔴 re-labels itself when the locale changes, like ok-data-table already does', async () => {
    const { wrapper, i18n } = mountDashboard('en');
    await flushPromises();
    expect(boardOf(wrapper).labels?.customize).toBe('Customize panel');

    i18n.global.locale.value = 'es';
    await nextTick();
    await flushPromises();

    expect(boardOf(wrapper).labels?.customize).toBe('Personalizar panel');
    expect(boardOf(wrapper).labels?.empty).toBe('Panel vacío. Pulsa ⋮ para añadir widgets.');
  });
});

// ── sales#473 · The «Recommended» preset the shell builds speaks the language of the UI ─────────
describe('the preset the shell names follows the language the user picks (sales#473)', () => {
  const recommendedAsked = (): unknown[] =>
    collectDashboardWidgets.mock.calls.map((c) => (c[0] as { labels?: { recommended?: string } }).labels?.recommended);

  it('🔴 asks the collector for the preset name in English on an English hub', async () => {
    mountDashboard('en');
    await flushPromises();
    expect(recommendedAsked().at(-1)).toBe('Recommended');
  });

  it('🔴 asks for it again, in Spanish, when the user switches to Spanish', async () => {
    const { i18n } = mountDashboard('en');
    await flushPromises();
    i18n.global.locale.value = 'es';
    await nextTick();
    await flushPromises();
    expect(recommendedAsked().at(-1)).toBe('Recomendado');
  });
});

// ── hub#1100 · El shell dice QUÉ arranca activo; la librería no lo adivina ─────────────────────
//
// 🔴 `ok-widget-board` documenta su último recurso: «sin `value` y sin presets ⇒ activa TODOS».
// El shell nunca le pasaba `value`, así que un hub sin sector (el caso normal desde ADR-0087:
// `HUB_SECTOR` ya no lo inyecta el provisioning) abría con los 20 widgets encendidos. El arreglo
// es dejar de depender de ese último recurso: el catálogo va completo, pero el conjunto ACTIVO
// se le entrega explícitamente.
describe('hub#1100 — el board arranca sólo con lo que el shell marca como activo', () => {
  beforeEach(() => {
    localStorage.clear();
    collectDashboardWidgets.mockResolvedValue({
      widgets: [
        { id: 'sales.today', title: 'Ventas de hoy', size: 'sm', render: () => {} },
        { id: 'sales.last_7_days', title: 'Últimos 7 días', size: 'md', render: () => {} },
        { id: 'verifactu.events', title: 'Eventos AEAT', size: 'md', render: () => {} },
      ],
      presets: [],
      defaultActive: ['sales.today'],
    });
  });

  // Since hub#2199 the core «set up your business» tile only joins an EMPTY business; these hubs
  // have apps (their modules hand widgets), so what starts active is exactly what they recommend.
  it('🔴 recibe `value` = los activos por defecto, NO el catálogo entero', async () => {
    setupStatusRef.value = statusWithApps('done');
    const { wrapper } = mountDashboard();
    await flushPromises();
    const board = boardOf(wrapper);
    expect(board.widgets?.length).toBe(3); // catálogo completo de módulo
    expect(board.value).toEqual(['sales.today']);
  });

  it('🔴 sin nada recomendado, el board arranca VACÍO (no con todo)', async () => {
    setupStatusRef.value = statusWithApps('done');
    collectDashboardWidgets.mockResolvedValue({
      widgets: [
        { id: 'sales.today', title: 'Ventas de hoy', size: 'sm', render: () => {} },
        { id: 'verifactu.events', title: 'Eventos AEAT', size: 'md', render: () => {} },
      ],
      presets: [],
      defaultActive: [],
    });
    const { wrapper } = mountDashboard();
    await flushPromises();
    // Before hub#2199 the core tile was what kept this `value` from being empty. Without it, an
    // empty `value` would be read by the board as «not given» and light up the whole catalogue.
    expect(whatTheBoardShows(boardOf(wrapper))).toEqual([]);
  });

  it('🔴 NO pisa lo que el usuario ya activó: al cambiar de idioma el `value` se respeta', async () => {
    const { wrapper, i18n } = mountDashboard('es');
    await flushPromises();
    const board = boardOf(wrapper) as BoardEl & { value?: string[] };
    // Lo que hace el usuario en el ⋮: el propio board reescribe su `value` (y lo persiste).
    board.value = ['verifactu.events'];

    i18n.global.locale.value = 'en';
    await nextTick();
    await flushPromises();

    expect(boardOf(wrapper).labels?.customize).toBe('Customize panel'); // el re-apply SÍ ocurrió
    expect((boardOf(wrapper) as BoardEl & { value?: string[] }).value).toEqual(['verifactu.events']);
  });

  it('un board recién montado tras el round trip vuelve a recibir su conjunto activo', async () => {
    setupStatusRef.value = statusWithApps('done');
    const { wrapper } = mountDashboard();
    await flushPromises();
    await roundTripThroughActivity(wrapper);
    expect(boardOf(wrapper).value).toEqual(['sales.today']);
  });
});

// ── hub#2199 · «Configura tu negocio» only while the business is still empty ───────────────────
//
// 🔴 The core tile («Set up your business — load a template or restore a backup to get started»)
// went into the catalogue, every preset and the default set UNCONDITIONALLY. A hub with the
// hairdresser template already applied still opened on it, inviting the owner to import a second
// template on top of a running business. It now follows the SAME rule as the hero card above it
// (`hubIsEmpty`, one read of `hub.setup.status`): offered while the business has no apps, gone from
// the CATALOGUE once it has — out of the catalogue, not merely out of the default set, because a
// layout the board saved earlier would otherwise keep painting it. Templates stay in Settings › Data.
describe('hub#2199 — the «set up your business» tile belongs to an empty business only', () => {
  const MODULE_WIDGETS = {
    widgets: [{ id: 'sales.today', title: 'Ventas de hoy', size: 'sm', render: () => {} }],
    presets: [{ id: 'recommended', label: 'Recomendado', widgets: ['sales.today'] }],
    defaultActive: ['sales.today'],
  };
  const NO_MODULES = { widgets: [], presets: [], defaultActive: [] };
  const ids = (board: BoardEl) => (board.widgets ?? []).map((w) => w.id);

  beforeEach(() => {
    localStorage.clear();
  });

  it('is offered, and shown, while the business has no apps', async () => {
    collectDashboardWidgets.mockResolvedValue(NO_MODULES);
    setupStatusRef.value = statusWithApps('pending');
    const { wrapper } = mountDashboard();
    await flushPromises();
    expect(ids(boardOf(wrapper))).toEqual(['core.blueprint']);
    expect(whatTheBoardShows(boardOf(wrapper))).toEqual(['core.blueprint']);
  });

  it('🔴 is NOT in the catalogue once a template has given the business its apps', async () => {
    collectDashboardWidgets.mockResolvedValue(MODULE_WIDGETS);
    setupStatusRef.value = statusWithApps('done');
    const { wrapper } = mountDashboard();
    await flushPromises();
    const board = boardOf(wrapper);
    expect(ids(board)).not.toContain('core.blueprint');
    expect(board.presets?.[0].widgets).not.toContain('core.blueprint');
    expect(whatTheBoardShows(board)).toEqual(['sales.today']);
  });

  it('🔴 is not offered while the status is unknown: an absence is not an empty business', async () => {
    collectDashboardWidgets.mockResolvedValue(MODULE_WIDGETS);
    const { wrapper } = mountDashboard();
    await flushPromises();
    expect(ids(boardOf(wrapper))).not.toContain('core.blueprint');
  });

  it('🔴 comes up when the status answers «empty» AFTER the widgets were collected', async () => {
    collectDashboardWidgets.mockResolvedValue(NO_MODULES);
    const { wrapper } = mountDashboard();
    await flushPromises();
    setupStatusRef.value = statusWithApps('pending');
    await flushPromises();
    expect(whatTheBoardShows(boardOf(wrapper))).toEqual(['core.blueprint']);
  });

  it('🔴 keeps the board loading until the status has answered, so the tile never pops in late', async () => {
    collectDashboardWidgets.mockResolvedValue(NO_MODULES);
    let answer: () => void = () => {};
    vi.mocked(refreshSetupStatus).mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          answer = resolve;
        }),
    );
    const { wrapper } = mountDashboard();
    await flushPromises();
    // The widgets are in, the status is not: the board is still behind its loading state (v-show).
    expect(boardOf(wrapper).style.display).toBe('none');

    setupStatusRef.value = statusWithApps('pending');
    answer();
    await flushPromises();
    expect(boardOf(wrapper).style.display).not.toBe('none');
    expect(whatTheBoardShows(boardOf(wrapper))).toEqual(['core.blueprint']);
  });

  it('🔴 a collection that omits `defaultActive` still dresses the board, starting empty', async () => {
    // What the view did before hub#2199 too: a partial answer degrades inside `loadWidgets`, it
    // never throws later from the board's watcher (the gate caught that as an unhandled rejection).
    collectDashboardWidgets.mockResolvedValue({
      widgets: MODULE_WIDGETS.widgets,
      presets: [],
    });
    setupStatusRef.value = statusWithApps('done');
    const { wrapper } = mountDashboard();
    await flushPromises();
    expect(ids(boardOf(wrapper))).toEqual(['sales.today']);
    expect(whatTheBoardShows(boardOf(wrapper))).toEqual([]);
  });

  it('🔴 leaves the board when the template is applied while the panel is on screen', async () => {
    collectDashboardWidgets.mockResolvedValue(NO_MODULES);
    setupStatusRef.value = statusWithApps('pending');
    const { wrapper } = mountDashboard();
    await flushPromises();
    expect(whatTheBoardShows(boardOf(wrapper))).toEqual(['core.blueprint']);

    // What an import does: apps installed (`erp:modules-changed`) and the status re-read.
    collectDashboardWidgets.mockResolvedValue(MODULE_WIDGETS);
    window.dispatchEvent(new Event('erp:modules-changed'));
    setupStatusRef.value = statusWithApps('done');
    await flushPromises();

    const board = boardOf(wrapper);
    expect(ids(board)).not.toContain('core.blueprint');
    // …and the untouched board moves on to what the new apps recommend, not to an empty panel.
    expect(whatTheBoardShows(board)).toEqual(['sales.today']);
  });

  it('never overrides a layout the user already chose when the tile leaves', async () => {
    collectDashboardWidgets.mockResolvedValue(MODULE_WIDGETS);
    setupStatusRef.value = statusWithApps('pending');
    const { wrapper } = mountDashboard();
    await flushPromises();
    const board = boardOf(wrapper);
    board.value = ['sales.today', 'core.blueprint']; // what the ⋮ writes

    setupStatusRef.value = statusWithApps('done');
    await flushPromises();

    expect(boardOf(wrapper).value).toEqual(['sales.today', 'core.blueprint']);
    expect(whatTheBoardShows(boardOf(wrapper))).toEqual(['sales.today']);
  });
});

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
import { nextTick, ref } from 'vue';

// ── Doubles for everything the view reaches for; none of it is what is under test ──────────────
const queryPage = vi.fn(async (..._args: unknown[]) => ({
  rows: [], total: 0, limit: 100, offset: 0,
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
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn(), setupStatus: ref(null) }));
vi.mock('../lib/shell', () => ({ openAssistantForSetup: vi.fn() }));
vi.mock('../lib/bridge-transport', () => ({ detectPeripherals: async () => null }));
vi.mock('../lib/system-health', () => ({ printerLine: () => null, probeFromBridge: () => null }));
vi.mock('../lib/dashboard-heading', () => ({
  GREETING_KEY: { morning: 'dashboard.morning' },
  panelHeading: () => ({ kind: 'business', name: 'Bar Manolo SL' }),
}));
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({ business_legal_name: 'Bar Manolo SL', country_code: 'ES', language: 'es' }),
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
    },
  },
};

type BoardEl = HTMLElement & {
  widgets?: unknown[];
  presets?: unknown[];
  labels?: Record<string, string>;
};
type Vm = { tab: 'resumen' | 'actividad' };

function mountDashboard(locale = 'es') {
  const i18n = createI18n({
    legacy: false, locale, missingWarn: false, fallbackWarn: false, messages,
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
  collectDashboardWidgets.mockResolvedValue({
    widgets: [{ id: 'sales.today', title: 'Ventas de hoy', size: 'sm', render: () => {} }],
    presets: [{ id: 'recommended', label: 'Recomendado', widgets: ['sales.today'] }],
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

  it('🔴 recibe `value` = widget core + los activos por defecto, NO el catálogo entero', async () => {
    const { wrapper } = mountDashboard();
    await flushPromises();
    const board = boardOf(wrapper) as BoardEl & { value?: string[] };
    expect(board.widgets?.length).toBe(4); // catálogo completo: core + 3 de módulo
    expect(board.value).toEqual(['core.blueprint', 'sales.today']);
  });

  it('🔴 sin nada recomendado, el board arranca sólo con el widget core (no con todo)', async () => {
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
    const board = boardOf(wrapper) as BoardEl & { value?: string[] };
    expect(board.value).toEqual(['core.blueprint']);
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
    const { wrapper } = mountDashboard();
    await flushPromises();
    await roundTripThroughActivity(wrapper);
    const board = boardOf(wrapper) as BoardEl & { value?: string[] };
    expect(board.value).toEqual(['core.blueprint', 'sales.today']);
  });
});

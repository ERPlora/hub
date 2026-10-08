// @vitest-environment happy-dom
// hub#2590 — Home › Activity names the payment method the way the Sales history does.
//
// The feed copied `payment_method_name` straight from `sales.list`, and `sales` seeds its factory
// methods in canonical English (ADR-0055): a cash sale read «Cash» on a Spanish hub while the Sales
// history, a tap away, read «Efectivo». The word has ONE source — `sales`' own catalogue
// (`locales/<lang>.json` → `ui.cash` / `ui.card`, what its `payMethodDisplayName` reads) — and one
// rule: a factory name is translated, a name the owner typed is kept.
//
// The view is mounted (shallow) and the `<ok-data-table>` is read through its properties: the row's
// `method` is both the cell and the source of the «Method» filter's options.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const queryPage = vi.fn();
const loadModuleLocale = vi.fn();
const active = { ids: new Set(['sales']) };

vi.mock('@ionic/vue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@ionic/vue')>();
  return { ...actual, onIonViewWillEnter: () => {}, onIonViewDidLeave: () => {} };
});
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ path: '/dashboard', hash: '#actividad' }),
}));
vi.mock('../lib/runtime', () => ({
  getClient: () => ({ queryPage: (...args: unknown[]) => queryPage(...args) }),
  getHubSector: () => 'restaurante',
  listInstalledModules: async () => [],
  activeModuleIds: () => active.ids,
  refreshActiveModuleIds: async () => {},
}));
vi.mock('../lib/module-loader', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/module-loader')>();
  return { ...actual, loadModuleLocale: (...args: unknown[]) => loadModuleLocale(...args) };
});
vi.mock('../lib/print-coverage', () => ({ fetchPrintHosts: async () => ({ coverage: [] }) }));
vi.mock('../lib/whatsapp-connect', () => ({ fetchWhatsAppNumbers: async () => [] }));
vi.mock('../lib/dashboard-widgets', () => ({ collectDashboardWidgets: async () => ({ widgets: [], presets: [] }) }));
vi.mock('../lib/dashboard-blueprint-widget', () => ({ buildBlueprintWidget: vi.fn() }));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]), moduleNavState: ref('ready') }));
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn(), setupStatus: ref(null) }));
vi.mock('../lib/shell', () => ({ openAssistantForSetup: vi.fn() }));
vi.mock('../lib/bridge-transport', () => ({ detectPeripherals: async () => null }));
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({ business_legal_name: 'Bar Pepe', country_code: 'ES', language: 'es', currency: 'EUR' }),
  publishedHubTimezone: () => null,
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));

// The real element, so `rows`/`columns` land as properties (an unknown tag would get them as attributes).
import '@erplora/outfitkit/ok-data-table';

import DashboardPage from './DashboardPage.vue';
import { activityMethodName } from '../lib/dashboard-activity';

type Row = Record<string, unknown>;
type TableEl = HTMLElement & { rows?: Row[] };

// `sales`' own catalogue, as `locales/<lang>.json` ships it (only the block this screen reads).
const SALES_CATALOGUE: Record<string, { ui: Record<string, string> }> = {
  en: { ui: { cash: 'Cash', card: 'Card' } },
  es: { ui: { cash: 'Efectivo', card: 'Tarjeta' } },
};

const SALES = [
  { id: 's1', sale_number: 'T-0001', total: 1250, status: 'completed', payment_method_name: 'Cash' },
  { id: 's2', sale_number: 'T-0002', total: 380, status: 'completed', payment_method_name: 'Card' },
  { id: 's3', sale_number: 'T-0003', total: 900, status: 'completed', payment_method_name: 'BBVA TPV' },
];
const page = (rows: Row[]) => ({ rows, total: rows.length, limit: 100, offset: 0 });

const mounted: VueWrapper[] = [];
function mountDashboard(locale: 'en' | 'es' = 'es') {
  const i18n = createI18n({ legacy: false, locale, missingWarn: false, fallbackWarn: false, messages: { en, es } });
  const wrapper = mount(DashboardPage, { global: { plugins: [i18n], renderStubDefaultSlot: true }, shallow: true });
  mounted.push(wrapper);
  return { wrapper, i18n };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 3; i++) {
    await flushPromises();
    await nextTick();
  }
}

function method(w: VueWrapper, saleNumber: string): unknown {
  const found = w.find('ok-data-table');
  expect(found.exists(), 'the activity table is on screen').toBe(true);
  const row = ((found.element as TableEl).rows ?? []).find((r) => r.sale === saleNumber);
  expect(row, `sale ${saleNumber} is listed`).toBeTruthy();
  return row!.method;
}

beforeEach(() => {
  active.ids = new Set(['sales']);
  queryPage.mockReset().mockResolvedValue(page(SALES));
  loadModuleLocale.mockReset().mockImplementation(async (_base: string, lang: string) => SALES_CATALOGUE[lang]);
});
afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount();
});

describe('Home › Activity names the method like the Sales history (hub#2590)', () => {
  it('hub2590: a cash sale reads «Efectivo» and a card sale «Tarjeta» in Spanish, not «Cash»/«Card»', async () => {
    const { wrapper } = mountDashboard('es');
    await settle();

    expect(method(wrapper, 'T-0001')).toBe('Efectivo');
    expect(method(wrapper, 'T-0002')).toBe('Tarjeta');
  });

  it('hub2590: the words come from the Sales catalogue, in the language on screen', async () => {
    const { wrapper } = mountDashboard('es');
    await settle();

    expect(loadModuleLocale).toHaveBeenCalledWith('/modules/sales', 'es');
    expect(method(wrapper, 'T-0001')).toBe('Efectivo');
  });

  it('hub2590: in English the factory names read in English', async () => {
    const { wrapper } = mountDashboard('en');
    await settle();

    expect(method(wrapper, 'T-0001')).toBe('Cash');
    expect(method(wrapper, 'T-0002')).toBe('Card');
  });

  it('hub2590: switching the language repaints the method in the new one', async () => {
    const { wrapper, i18n } = mountDashboard('es');
    await settle();
    expect(method(wrapper, 'T-0001')).toBe('Efectivo');

    i18n.global.locale.value = 'en';
    await settle();

    expect(method(wrapper, 'T-0001')).toBe('Cash');
  });

  it('hub2590: a method the business renamed keeps the name the owner typed', async () => {
    const { wrapper } = mountDashboard('es');
    await settle();

    expect(method(wrapper, 'T-0003')).toBe('BBVA TPV');
  });

  it('hub2590: without the Sales catalogue the method keeps its stored name, never a blank or a key', async () => {
    loadModuleLocale.mockReset().mockResolvedValue(undefined);
    const { wrapper } = mountDashboard('es');
    await settle();

    expect(method(wrapper, 'T-0001')).toBe('Cash');
    expect(method(wrapper, 'T-0003')).toBe('BBVA TPV');
  });

  it('hub2590: a slow read for the previous language does not overwrite the language on screen', async () => {
    let answerSpanish: (v: unknown) => void = () => {};
    loadModuleLocale
      .mockReset()
      .mockImplementation((_base: string, lang: string) =>
        lang === 'es' ? new Promise((resolve) => (answerSpanish = resolve)) : Promise.resolve(SALES_CATALOGUE[lang]),
      );
    const { wrapper, i18n } = mountDashboard('es');
    await settle();

    i18n.global.locale.value = 'en';
    await settle();
    answerSpanish(SALES_CATALOGUE.es);
    await settle();

    expect(method(wrapper, 'T-0001')).toBe('Cash');
  });

  it('hub2590: a hub without Sales does not ask for its catalogue, not even on a language switch', async () => {
    active.ids = new Set(['appointments']);
    queryPage.mockReset().mockResolvedValue(page([]));
    const { i18n } = mountDashboard('es');
    await settle();
    i18n.global.locale.value = 'en';
    await settle();

    expect(loadModuleLocale).not.toHaveBeenCalledWith('/modules/sales', expect.anything());
  });
});

describe('activityMethodName — the Sales rule, unit by unit (hub#2590)', () => {
  const ui = SALES_CATALOGUE.es.ui;

  it('hub2590: a factory name with stray spaces is still the factory method, as Sales reads it', () => {
    expect(activityMethodName(' Cash ', ui)).toBe('Efectivo');
  });

  it('hub2590: an empty word in the catalogue falls back to the stored name', () => {
    expect(activityMethodName('Cash', { cash: '  ' })).toBe('Cash');
  });
});

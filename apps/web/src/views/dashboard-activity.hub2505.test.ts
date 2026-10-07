// @vitest-environment happy-dom
// hub#2505 — Home › Activity, as the screen paints it (the lib half is `lib/dashboard-activity.hub2505.test.ts`).
//
// Three defects on one tab:
//   1. every sale read a hundred times bigger: `sales.list` serves `total` in cents and the view
//      painted it with `formatAmount` (amounts already in euros) — 12,50 € read «1.250,00 €»;
//   2. every sale that was not completed — voided, refunded, open — read «Pending»;
//   3. a failed read painted the table empty, as if the business had sold nothing.
//
// The view is mounted (shallow) and the `<ok-data-table>` is read through its properties, the way
// the Apps tests do: the column's own `format`/`render` is what reaches the screen.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const queryPage = vi.fn();

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
  activeModuleIds: () => new Set(['sales']),
  refreshActiveModuleIds: async () => {},
}));
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

// CLDR puts a NO-BREAK SPACE (U+00A0) between the figure and the € in Spanish.
const NBSP = '\u00a0';

type Row = Record<string, unknown>;
type Column = { key: string; format?: (r: Row) => string; render?: (r: Row) => unknown };
type TableEl = HTMLElement & { rows?: Row[]; columns?: Column[] };

const SALES = [
  { id: 's1', sale_number: 'T-0001', total: 1250, status: 'completed', payment_method_name: 'Cash' },
  { id: 's2', sale_number: 'T-0002', total: 380, status: 'voided', payment_method_name: 'Card' },
];
const page = (rows: Row[]) => ({ rows, total: rows.length, limit: 100, offset: 0 });

const mounted: VueWrapper[] = [];
function mountDashboard(locale: 'en' | 'es' = 'es') {
  const i18n = createI18n({ legacy: false, locale, missingWarn: false, fallbackWarn: false, messages: { en, es } });
  const wrapper = mount(DashboardPage, { global: { plugins: [i18n], renderStubDefaultSlot: true }, shallow: true });
  mounted.push(wrapper);
  return wrapper;
}

async function settle(): Promise<void> {
  for (let i = 0; i < 3; i++) {
    await flushPromises();
    await nextTick();
  }
}

const table = (w: VueWrapper): TableEl | undefined => {
  const found = w.find('ok-data-table');
  return found.exists() ? (found.element as TableEl) : undefined;
};
function cell(w: VueWrapper, key: string, saleNumber: string): string {
  const t = table(w);
  expect(t, 'the activity table is on screen').toBeTruthy();
  const row = (t!.rows ?? []).find((r) => r.sale === saleNumber);
  expect(row, `sale ${saleNumber} is listed`).toBeTruthy();
  const column = (t!.columns ?? []).find((c) => c.key === key)!;
  if (column.format) return column.format(row!);
  const painted = column.render ? column.render(row!) : row![key];
  return typeof painted === 'string' ? painted : ((painted as HTMLElement).textContent ?? '');
}
const loadError = (w: VueWrapper) => w.find('[data-testid="dashboard-activity-load-error"]');

beforeEach(() => {
  queryPage.mockReset().mockResolvedValue(page(SALES));
});
afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount();
});

describe('Home › Activity paints each sale with its real amount (hub#2505)', () => {
  it('a 12,50 € sale reads «12,50 €», not «1.250,00 €»', async () => {
    const w = mountDashboard('es');
    await settle();

    expect(cell(w, 'amount', 'T-0001')).toBe(`12,50${NBSP}€`);
    expect(cell(w, 'amount', 'T-0002')).toBe(`3,80${NBSP}€`);
  });

  it('in English too, with English separators', async () => {
    const w = mountDashboard('en');
    await settle();

    expect(cell(w, 'amount', 'T-0001')).toBe('€12.50');
  });

  it('a voided sale says «Anulada», not «Pendiente»', async () => {
    const w = mountDashboard('es');
    await settle();

    expect(cell(w, 'status', 'T-0001')).toBe('Completada');
    expect(cell(w, 'status', 'T-0002')).toBe('Anulada');
  });
});

describe('Home › Activity says when it could not read the sales (hub#2505)', () => {
  it('a failed first read says so instead of an empty table', async () => {
    queryPage.mockReset().mockRejectedValue(new Error('network down'));
    const w = mountDashboard('es');
    await settle();

    expect(loadError(w).exists(), 'the failure is said').toBe(true);
    expect(table(w), 'no empty table under the failure').toBeUndefined();
  });

  it('«Retry» reads again and paints the sales once the hub answers', async () => {
    queryPage.mockReset().mockRejectedValueOnce(new Error('network down')).mockResolvedValue(page(SALES));
    const w = mountDashboard('es');
    await settle();

    await w.find('[data-testid="dashboard-activity-retry"]').trigger('click');
    await settle();

    expect(loadError(w).exists()).toBe(false);
    expect(cell(w, 'amount', 'T-0001')).toBe(`12,50${NBSP}€`);
  });

  it('a refresh that fails keeps the sales already on screen and says it could not update', async () => {
    const w = mountDashboard('es');
    await settle();
    expect(cell(w, 'amount', 'T-0001')).toBe(`12,50${NBSP}€`);

    queryPage.mockRejectedValue(new Error('network down'));
    window.dispatchEvent(new Event('erp:modules-changed'));
    await settle();

    expect(loadError(w).exists(), 'the failure is said').toBe(true);
    expect(cell(w, 'amount', 'T-0001'), 'the last good list stays').toBe(`12,50${NBSP}€`);
  });
});

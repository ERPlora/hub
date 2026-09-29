// @vitest-environment happy-dom
//
// hub#2387 (from ERPlora/outfitkit#243): the money panels of the home page (kpi, stat, sparkline
// kpi, bar-list) painted EVERY amount in euros — `options.currency ?? 'EUR'` — and scaled it by a
// fixed ÷100, even when the hub works in another currency. A business in dollars saw its home page
// in euros while the till and the receipts used dollars; a business in yen saw 1999 ¥ as 19,99.
//
// Contract: when the panel does not set a currency, the home page uses the HUB's currency, scaled
// by the minor unit of that currency (EUR 2, JPY 0, KWD 3 — ADR-0123 §7), and formatted in the
// language of the UI when the panel does not set a locale (the same rule as `lib/money.ts` and as
// `ok-bar-list`, which follows `<html lang>`). A currency the panel does set is still painted.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Same isolation as dashboard-widgets.test.ts: `module-loader` drags the `~icons/…?raw` chain that
// the vitest transform denies. Only its I/O functions are stubbed; the rows are real shapes.
vi.mock('./module-loader', () => ({
  loadInstalledManifests: vi.fn(),
  loadModuleComponent: vi.fn(),
}));

import { buildWidgetsFromManifests } from './dashboard-widgets';
import { hubSettings, type HubSettings } from './hub-settings';
import { i18n } from '../i18n';
import type { InstalledManifest } from './module-loader';
import type { ErploraClient } from '@erplora/module-sdk';
import type { WidgetManifestDef } from '@erplora/module-types';

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

async function renderOne(def: WidgetManifestDef, rows: unknown[]): Promise<HTMLElement> {
  const manifests = [
    { id: 'cash_register', manifest: { id: 'cash_register', widgets: { w: def } } },
  ] as unknown as InstalledManifest[];
  const client = { query: vi.fn(async () => rows), on: () => () => {} } as unknown as ErploraClient;
  const { widgets } = buildWidgetsFromManifests(manifests, { client, sector: null });
  const cell = document.createElement('div');
  widgets[0]!.render(cell);
  await flush();
  return cell;
}

/** Intl separates amount and symbol with a no-break space; normalise it for the literals. */
const plain = (s: string | undefined): string | undefined => s?.replace(/[  ]/g, ' ');

function kpiValue(cell: HTMLElement): string | undefined {
  return plain((cell.querySelector('ok-kpi') as (HTMLElement & { value?: string }) | null)?.value);
}

function statValue(cell: HTMLElement): string | undefined {
  return plain((cell.querySelector('ok-stat') as (HTMLElement & { value?: string }) | null)?.value);
}

type BarList = HTMLElement & {
  items?: Array<{ label: string; value: number }>;
  currency?: string;
  locale?: string;
};
const barList = (cell: HTMLElement): BarList | null => cell.querySelector('ok-bar-list');

function hubIn(currency: string, currency_decimals?: number): void {
  hubSettings.value = { currency, currency_decimals } as unknown as HubSettings;
}

const kpi = (options: Record<string, unknown>): WidgetManifestDef => ({
  title: 'Expected cash in drawer',
  kind: 'kpi',
  query: 'cash_register.sessions.current',
  map: { value: 'expected' },
  options: { format: 'currency', ...options },
});

const barListDef = (options: Record<string, unknown>): WidgetManifestDef => ({
  title: 'Recent cash discrepancies',
  kind: 'bar-list',
  query: 'cash_register.sessions.list',
  map: { label: 'session_number', value: 'difference' },
  options: { valueFormat: 'currency', ...options },
});

let savedLocale: string;
beforeEach(() => {
  savedLocale = i18n.global.locale.value;
});
afterEach(() => {
  hubSettings.value = null;
  i18n.global.locale.value = savedLocale;
});

describe('hub#2387 — the home page paints money in the currency of the hub', () => {
  it('a kpi without currency uses the hub currency (dollars), not euros', async () => {
    hubIn('USD', 2);
    const cell = await renderOne(kpi({ locale: 'es-ES' }), [{ expected: 150 }]);
    expect(kpiValue(cell)).toBe('1,50 US$');
  });

  it('a kpi in a yen hub does not divide by 100: 999 is 999 ¥', async () => {
    hubIn('JPY', 0);
    const cell = await renderOne(kpi({ locale: 'es-ES' }), [{ expected: 999 }]);
    expect(kpiValue(cell)).toBe('999 JPY');
  });

  it('a kpi in a dinar hub keeps three decimals: 12345 is 12,345 KWD', async () => {
    hubIn('KWD', 3);
    const cell = await renderOne(kpi({ locale: 'es-ES' }), [{ expected: 12345 }]);
    expect(kpiValue(cell)).toBe('12,345 KWD');
  });

  it('the scale is the one the hub declares, even when it differs from the ISO registry', async () => {
    // The runtime resolves `currency_decimals` (registry OR what the hub declared by hand): the
    // shell trusts it for the hub currency instead of re-deriving it.
    hubIn('JPY', 2);
    const cell = await renderOne(kpi({ locale: 'es-ES' }), [{ expected: 999 }]);
    // ÷100 by the declared scale (the registry would say ÷1 → «999 JPY»); JPY paints no decimals.
    expect(kpiValue(cell)).toBe('10 JPY');
  });

  it('a currency the panel sets is still honoured', async () => {
    // Same rule as `formatMoney`: the scale is the hub's (the amounts are minor units of the hub
    // currency), the panel only chooses the currency that is PAINTED.
    hubIn('USD', 2);
    const cell = await renderOne(kpi({ currency: 'EUR', locale: 'es-ES' }), [{ expected: 150 }]);
    expect(kpiValue(cell)).toBe('1,50 €');
  });

  it('without a locale, the kpi follows the language of the UI (not a fixed es-ES)', async () => {
    hubIn('USD', 2);
    i18n.global.locale.value = 'en';
    const en = await renderOne(kpi({}), [{ expected: 150 }]);
    expect(kpiValue(en)).toBe('$1.50');

    i18n.global.locale.value = 'es';
    const es = await renderOne(kpi({}), [{ expected: 150 }]);
    expect(kpiValue(es)).toBe('1,50 US$');
  });

  it('a stat without currency uses the hub currency', async () => {
    hubIn('USD', 2);
    i18n.global.locale.value = 'es';
    const def: WidgetManifestDef = {
      title: 'Takings',
      kind: 'stat',
      query: 'sales.stats.today',
      map: { value: 'total' },
      options: { format: 'currency' },
    };
    const cell = await renderOne(def, [{ total: 150 }]);
    expect(statValue(cell)).toBe('1,50 US$');
  });

  it('the kpi of a sparkline without currency uses the hub currency', async () => {
    hubIn('JPY', 0);
    i18n.global.locale.value = 'es';
    const def: WidgetManifestDef = {
      title: 'Last 7 days',
      kind: 'sparkline',
      query: 'sales.last_7_days',
      map: { series: 'total', value: 'total' },
      options: { format: 'currency' },
    };
    const cell = await renderOne(def, [{ total: 100 }, { total: 999 }]);
    expect(kpiValue(cell)).toBe('999 JPY');
  });

  it('a bar-list without currency gets the hub currency', async () => {
    hubIn('USD', 2);
    const cell = await renderOne(barListDef({}), [{ session_number: 'S-1', difference: -40 }]);
    expect(barList(cell)?.currency).toBe('USD');
  });

  it('a money bar-list is scaled by the minor unit of the hub currency, like the kpi', async () => {
    hubIn('EUR', 2);
    const eur = await renderOne(barListDef({}), [{ session_number: 'S-1', difference: -40 }]);
    expect(barList(eur)?.items?.[0]?.value).toBe(-0.4);

    hubIn('JPY', 0);
    const yen = await renderOne(barListDef({}), [{ session_number: 'S-1', difference: -500 }]);
    expect(barList(yen)?.items?.[0]?.value).toBe(-500);
  });

  it('a money bar-list that declares valueDivisor 100 is not divided twice, and not by 100 in yen', async () => {
    // cash_register declares `valueDivisor: 100` for its discrepancies (cash_register#120): the
    // scale of money is a property of the currency, not of the module.
    hubIn('EUR', 2);
    const eur = await renderOne(barListDef({ valueDivisor: 100 }), [{ session_number: 'S-1', difference: -550 }]);
    expect(barList(eur)?.items?.[0]?.value).toBe(-5.5);

    hubIn('JPY', 0);
    const yen = await renderOne(barListDef({ valueDivisor: 100 }), [{ session_number: 'S-1', difference: -500 }]);
    expect(barList(yen)?.items?.[0]?.value).toBe(-500);
  });

  it('a bar-list without locale is formatted in the language of the UI', async () => {
    hubIn('USD', 2);
    i18n.global.locale.value = 'en';
    const cell = await renderOne(barListDef({}), [{ session_number: 'S-1', difference: -40 }]);
    expect(barList(cell)?.locale).toBe('en');
  });

  it('a bar-list that is not money keeps its declared divisor (stock at scale 10^6)', async () => {
    hubIn('JPY', 0);
    const def: WidgetManifestDef = {
      title: 'Low stock',
      kind: 'bar-list',
      query: 'inventory.products.low_stock',
      map: { label: 'name', value: 'stock' },
      options: { valueFormat: 'number', valueDivisor: 1_000_000 },
    };
    const cell = await renderOne(def, [{ name: 'Water', stock: 3_000_000 }]);
    expect(barList(cell)?.items?.[0]?.value).toBe(3);
  });
});

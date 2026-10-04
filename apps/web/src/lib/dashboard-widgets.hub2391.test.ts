// @vitest-environment happy-dom
//
// hub#2391 (from hub#2387): a money panel of the home page that SETS its own currency painted the
// symbol of that currency but scaled the amount by the decimals of the HUB currency. A panel in
// euros on a hub that works in yen divided by 1 instead of 100 (×100); a panel in yen on a hub in
// euros divided by 100 instead of 1 (÷100); a panel in dinars (3 decimals) on a hub in euros was ×10.
//
// Contract: the minor units of an amount belong to the currency that is PAINTED (the Stripe and
// ISO-4217 convention: an amount in minor units is always read with its currency). When the panel
// sets a currency, its decimals scale the amount; when it does not, the hub's (the ones the runtime
// resolves in `currency_decimals`, which may be declared by hand).
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

const valueOf = (cell: HTMLElement, tag: string): string | undefined =>
  plain((cell.querySelector(tag) as (HTMLElement & { value?: string }) | null)?.value);

function hubIn(currency: string, currency_decimals: number): void {
  hubSettings.value = { currency, currency_decimals } as unknown as HubSettings;
}

const money = (kind: 'kpi' | 'stat', currency: string): WidgetManifestDef => ({
  title: 'Takings',
  kind,
  query: 'sales.stats.today',
  map: { value: 'total' },
  options: { format: 'currency', currency, locale: 'es-ES' },
});

let savedLocale: string;
beforeEach(() => {
  savedLocale = i18n.global.locale.value;
  i18n.global.locale.value = 'es';
});
afterEach(() => {
  hubSettings.value = null;
  i18n.global.locale.value = savedLocale;
});

describe('hub#2391 — a panel that sets its currency is scaled by that currency', () => {
  it('a kpi in euros on a yen hub divides by 100 (not ×100)', async () => {
    hubIn('JPY', 0);
    const cell = await renderOne(money('kpi', 'EUR'), [{ total: 1999 }]);
    expect(valueOf(cell, 'ok-kpi')).toBe('19,99 €');
  });

  it('a kpi in yen on a euro hub does not divide by 100', async () => {
    hubIn('EUR', 2);
    const cell = await renderOne(money('kpi', 'JPY'), [{ total: 1999 }]);
    // Grouped from 4 digits (hub#1090).
    expect(valueOf(cell, 'ok-kpi')).toBe('1.999 JPY');
  });

  it('a stat in dinars on a euro hub keeps its three decimals', async () => {
    hubIn('EUR', 2);
    const cell = await renderOne(money('stat', 'KWD'), [{ total: 12345 }]);
    expect(valueOf(cell, 'ok-stat')).toBe('12,345 KWD');
  });

  it('the hub currency is recognised regardless of case, and keeps its declared scale', async () => {
    hubIn('JPY', 2);
    const cell = await renderOne(money('kpi', 'jpy'), [{ total: 999 }]);
    expect(valueOf(cell, 'ok-kpi')).toBe('10 JPY');
  });

  it('a panel that sets the hub currency keeps the scale the hub declares', async () => {
    // The runtime resolves `currency_decimals` (ISO registry OR what the hub declared by hand):
    // naming the hub currency in the panel must not fall back to the registry.
    hubIn('JPY', 2);
    const cell = await renderOne(money('kpi', 'JPY'), [{ total: 999 }]);
    expect(valueOf(cell, 'ok-kpi')).toBe('10 JPY');
  });

  it('the kpi of a sparkline in euros on a yen hub divides by 100', async () => {
    hubIn('JPY', 0);
    const def: WidgetManifestDef = {
      title: 'Last 7 days',
      kind: 'sparkline',
      query: 'sales.last_7_days',
      map: { series: 'total', value: 'total' },
      options: { format: 'currency', currency: 'EUR' },
    };
    const cell = await renderOne(def, [{ total: 100 }, { total: 1999 }]);
    expect(valueOf(cell, 'ok-kpi')).toBe('19,99 €');
  });

  it('a bar-list in euros on a yen hub hands euros to ok-bar-list', async () => {
    hubIn('JPY', 0);
    const def: WidgetManifestDef = {
      title: 'Recent cash discrepancies',
      kind: 'bar-list',
      query: 'cash_register.sessions.list',
      map: { label: 'session_number', value: 'difference' },
      options: { valueFormat: 'currency', currency: 'EUR' },
    };
    const cell = await renderOne(def, [{ session_number: 'S-1', difference: -550 }]);
    const list = cell.querySelector('ok-bar-list') as
      (HTMLElement & { items?: Array<{ value: number }>; currency?: string }) | null;
    expect(list?.currency).toBe('EUR');
    expect(list?.items?.[0]?.value).toBe(-5.5);
  });

  it('a chart in dinars on a yen hub is drawn and labelled in dinars', async () => {
    hubIn('JPY', 0);
    const def: WidgetManifestDef = {
      title: 'Sales, last 7 days',
      kind: 'chart',
      query: 'sales.last_7_days',
      map: { label: 'day', value: 'total' },
      options: { chartType: 'bar', format: 'currency', currency: 'KWD', locale: 'en-US' },
    };
    const cell = await renderOne(def, [{ day: '2026-09-29', total: 1500 }]);
    const chart = cell.querySelector('ok-chart') as
      (HTMLElement & { series?: Array<{ data: number[] }>; axis?: string[]; max?: number }) | null;
    expect(chart?.series?.[0]?.data).toEqual([1.5]);
    expect(chart?.max).toBe(1.5);
    expect(chart?.axis?.map((s) => plain(s))).toEqual(['KWD 1.5', 'KWD 1', 'KWD 0.5', 'KWD 0']);
  });
});

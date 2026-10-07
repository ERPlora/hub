// @vitest-environment happy-dom
//
// hub#2469 (from hub#2391): the axis of a money chart capped every tick at 2 decimals, so a
// 3-decimal currency (a dinar) with takings below 0,01 painted repeated or all-zero labels —
// 7 thousandths read «0,01 · 0,01 · 0 · 0 · 0» and 3 thousandths read «0 KWD» four times, while
// the scale itself did respect the millième. A tick now admits as many decimals as the painted
// currency has — and never fewer than 2, so the halves of a 2,5 step of a 0-decimal currency
// (7,5 ¥) keep rendering instead of rounding to «8 ¥».
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

/** Renders one bar chart of minor-unit totals in `currency` (omitted: the hub's) and returns its axis. */
async function renderChartAxis(currency: string | undefined, totals: number[]): Promise<string[]> {
  const def: WidgetManifestDef = {
    title: 'Takings',
    kind: 'chart',
    query: 'sales.last_7_days',
    map: { label: 'day', value: 'total' },
    options: { chartType: 'bar', format: 'currency', locale: 'es-ES', ...(currency ? { currency } : {}) },
  };
  const manifests = [{ id: 'sales', manifest: { id: 'sales', widgets: { w: def } } }] as unknown as InstalledManifest[];
  const rows = totals.map((total, i) => ({ day: `2026-09-2${i}`, total }));
  const client = { query: vi.fn(async () => rows), on: () => () => {} } as unknown as ErploraClient;
  const { widgets } = buildWidgetsFromManifests(manifests, { client, sector: null });
  const cell = document.createElement('div');
  widgets[0]!.render(cell);
  await flush();
  const chart = cell.querySelector('ok-chart') as (HTMLElement & { axis?: string[] }) | null;
  // Intl separates amount and symbol with no-break spaces (U+00A0, U+202F); written as escapes so
  // they survive being retyped into a literal — a plain space in the class normalises nothing.
  return (chart?.axis ?? []).map((s) => s.replace(/[\u00A0\u202F]/g, ' '));
}

function hubIn(currency: string, currency_decimals: number): void {
  hubSettings.value = { currency, currency_decimals } as unknown as HubSettings;
}

let savedLocale: string;
beforeEach(() => {
  savedLocale = i18n.global.locale.value;
  i18n.global.locale.value = 'es';
});
afterEach(() => {
  hubSettings.value = null;
  i18n.global.locale.value = savedLocale;
});

describe('hub#2469 — a chart axis shows the decimals of the currency it paints', () => {
  it('a dinar chart of 3 thousandths labels each tick with its thousandths', async () => {
    hubIn('EUR', 2);
    // 3 fils of a KWD panel: ticks at 0,003/0,002/0,001/0 KWD.
    expect(await renderChartAxis('KWD', [3])).toEqual(['0,003 KWD', '0,002 KWD', '0,001 KWD', '0 KWD']);
  });

  it('a dinar chart of 7 thousandths does not collapse its ticks into «0,01» and «0»', async () => {
    hubIn('JPY', 0);
    // The axis the issue measured: niceScale gives a 2-fils step for a 7-fils chart (5 marks), and
    // with the 2-decimal cap the gridline ticks at 0,008/0,006 both read «0,01 KWD» and 0,004/0,002
    // both read «0 KWD» — the labels lie about the scale they annotate.
    expect(await renderChartAxis('KWD', [7])).toEqual([
      '0,008 KWD', '0,006 KWD', '0,004 KWD', '0,002 KWD', '0 KWD',
    ]);
  });

  it('a chart in the hub currency (3 decimals) labels its ticks with those decimals', async () => {
    hubIn('KWD', 3);
    expect(await renderChartAxis(undefined, [3])).toEqual(['0,003 KWD', '0,002 KWD', '0,001 KWD', '0 KWD']);
  });

  it('a euro chart keeps its two decimals', async () => {
    hubIn('JPY', 0);
    // 3 cents: already right in the issue's probe; it must not grow a third decimal.
    expect(await renderChartAxis('EUR', [3])).toEqual(['0,03 €', '0,02 €', '0,01 €', '0 €']);
  });

  it('a yen chart keeps the halves of a 2,5 step (0 is not its decimals)', async () => {
    hubIn('EUR', 2);
    // niceScale gives a 2,5 ¥ step for a 10 ¥ total: those ticks are exact today and must stay so.
    expect(await renderChartAxis('JPY', [10])).toEqual(['10 JPY', '7,5 JPY', '5 JPY', '2,5 JPY', '0 JPY']);
  });

  it('a dinar chart of normal amounts stays compact', async () => {
    hubIn('EUR', 2);
    // 1234567 fils = 1234,567 KWD: with normal takings nothing changes (the issue's probe row).
    expect(await renderChartAxis('KWD', [1234567])).toEqual(['1,5 mil KWD', '1 mil KWD', '500 KWD', '0 KWD']);
  });
});

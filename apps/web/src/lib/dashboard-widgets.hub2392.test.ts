// @vitest-environment happy-dom
//
// hub#2392 (from ERPlora/sales#469): the «Sales, last 7 days» panel of the home page drew its bars
// without a single amount — no value axis, raw minor units handed to `ok-chart` — and wrote each
// day as `2026-09-29`. The shell ignored the `format` the panel declares on its charts.
//
// Contract: a `kind: chart` panel honours `options.format` like the kpi and the bar-list do (hub#2387):
// money is scaled by the minor unit of the hub currency and the value axis is painted in that
// currency (or the one the panel sets), in the language of the UI (or the locale the panel sets).
// The axis is a round scale that covers every value, and the chart is pinned to it so each tick
// sits on its gridline. ISO dates on the category axis are written in the language of the UI.
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

type Chart = HTMLElement & {
  series?: Array<{ name?: string; data: number[] }>;
  labels?: string[];
  axis?: string[];
  min?: number;
  max?: number;
};

async function renderChart(options: Record<string, unknown>, rows: unknown[]): Promise<Chart> {
  const def: WidgetManifestDef = {
    title: 'Sales, last 7 days',
    kind: 'chart',
    query: 'sales.last_7_days',
    map: { label: 'day', value: 'total' },
    options: { chartType: 'bar', seriesName: 'Sales', ...options },
  };
  const manifests = [
    { id: 'sales', manifest: { id: 'sales', widgets: { 'sales.last_7_days': def } } },
  ] as unknown as InstalledManifest[];
  const client = { query: vi.fn(async () => rows), on: () => () => {} } as unknown as ErploraClient;
  const { widgets } = buildWidgetsFromManifests(manifests, { client, sector: null });
  const cell = document.createElement('div');
  widgets[0]!.render(cell);
  await flush();
  const chart = cell.querySelector('ok-chart') as Chart | null;
  if (!chart) throw new Error('no ok-chart rendered');
  return chart;
}

/** Intl separates amount and symbol with a no-break space; normalise it for the literals. */
const plain = (xs: string[] | undefined): string[] | undefined => xs?.map((s) => s.replace(/[\u00a0\u202f]/g, ' '));

function hubIn(currency: string, currency_decimals?: number): void {
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

describe('hub#2392 — a chart panel honours the format it declares', () => {
  it('money is scaled by the hub currency and the value axis is painted in it', async () => {
    hubIn('EUR', 2);
    const chart = await renderChart({ format: 'currency' }, [
      { day: '2026-09-28', total: 30000 },
      { day: '2026-09-29', total: 184050 },
    ]);
    // Minor units → euros: the bars are drawn in the unit the axis speaks.
    expect(chart.series?.[0]?.data).toEqual([300, 1840.5]);
    // A round scale from 0 that covers 1.840,50 €, top to bottom (ok-chart's axis order).
    expect(plain(chart.axis)).toEqual(['2 mil €', '1,5 mil €', '1 mil €', '500 €', '0 €']);
    // The chart is pinned to that scale, so each label sits on its gridline.
    expect(chart.max).toBe(2000);
    expect(chart.min).toBe(0);
  });

  it('a yen hub does not divide by 100', async () => {
    hubIn('JPY', 0);
    const chart = await renderChart({ format: 'currency' }, [{ day: '2026-09-29', total: 1999 }]);
    expect(chart.series?.[0]?.data).toEqual([1999]);
    expect(plain(chart.axis)?.[0]).toBe('2 mil JPY');
    expect(chart.max).toBe(2000);
  });

  it('a yen scale never shows fractions of the minor unit', async () => {
    hubIn('JPY', 0);
    const chart = await renderChart({ format: 'currency' }, [{ day: '2026-09-29', total: 2 }]);
    expect(plain(chart.axis)).toEqual(['2 JPY', '1 JPY', '0 JPY']);
  });

  it('the axis follows the language of the UI', async () => {
    hubIn('USD', 2);
    i18n.global.locale.value = 'en';
    const chart = await renderChart({ format: 'currency' }, [{ day: '2026-09-29', total: 184050 }]);
    expect(plain(chart.axis)).toEqual(['$2K', '$1.5K', '$1K', '$500', '$0']);
  });

  it('a currency and a locale the panel sets are still honoured', async () => {
    // Declared values that differ from the defaults (hub in USD, UI in es): the panel wins on what
    // is PAINTED; the scale stays the hub's, like `formatMoney` (hub#2387).
    hubIn('USD', 2);
    const chart = await renderChart({ format: 'currency', currency: 'EUR', locale: 'en-US' }, [
      { day: '2026-09-29', total: 184050 },
    ]);
    expect(chart.series?.[0]?.data).toEqual([1840.5]);
    expect(plain(chart.axis)?.[0]).toBe('€2K');
    expect(chart.labels).toEqual(['Sep 29']);
  });

  it('a percent chart paints a percent axis', async () => {
    const chart = await renderChart({ format: 'percent' }, [
      { day: 'Mon', total: 0.2 },
      { day: 'Tue', total: 0.35 },
    ]);
    expect(chart.series?.[0]?.data).toEqual([0.2, 0.35]);
    expect(plain(chart.axis)?.[0]).toBe('40 %');
    expect(chart.max).toBeCloseTo(0.4);
  });

  it('a line chart that never touches 0 starts its scale at the lowest round value', async () => {
    const chart = await renderChart({ format: 'number', chartType: 'line' }, [
      { day: 'Mon', total: 820 },
      { day: 'Tue', total: 960 },
    ]);
    expect(chart.min).toBe(800);
    expect(chart.max).toBe(1000);
    expect(plain(chart.axis)).toEqual(['1 mil', '950', '900', '850', '800']);
  });

  it('an area chart grows from 0 like the bars, not from the lowest value', async () => {
    const chart = await renderChart({ format: 'number', chartType: 'area' }, [
      { day: 'Mon', total: 820 },
      { day: 'Tue', total: 960 },
    ]);
    expect(chart.min).toBe(0);
    expect(chart.max).toBe(1000);
  });

  it('a chart that is not money keeps the divisor it declares (quantities at scale 10^6)', async () => {
    const chart = await renderChart({ format: 'number', valueDivisor: 1_000_000 }, [
      { day: 'Mon', total: 2_500_000 },
      { day: 'Tue', total: 5_000_000 },
    ]);
    expect(chart.series?.[0]?.data).toEqual([2.5, 5]);
  });

  it('a chart without format keeps its raw values but still gets a readable axis', async () => {
    const chart = await renderChart({}, [
      { day: 'Mon', total: 1000 },
      { day: 'Tue', total: 2000 },
    ]);
    expect(chart.series?.[0]?.data).toEqual([1000, 2000]);
    expect(plain(chart.axis)).toEqual(['2 mil', '1,5 mil', '1 mil', '500', '0']);
  });

  it('a series of zeros still draws a scale instead of collapsing it', async () => {
    hubIn('EUR', 2);
    const chart = await renderChart({ format: 'currency' }, [{ day: '2026-09-29', total: 0 }]);
    // One euro of headroom split in quarters, not a collapsed 0–0 axis.
    expect(chart.min).toBe(0);
    expect(chart.max).toBe(1);
    expect(plain(chart.axis)).toEqual(['1 €', '0,75 €', '0,5 €', '0,25 €', '0 €']);
  });

  it('binary noise does not add an extra tick above the data', async () => {
    // 0.07 / 0.01 is 7.000000000000001 in floating point: rounded up blindly it would stretch the
    // scale to 8 % and leave the top of the chart empty.
    const chart = await renderChart({ format: 'percent', chartType: 'line' }, [
      { day: 'Mon', total: 0.05 },
      { day: 'Tue', total: 0.07 },
    ]);
    expect(chart.max).toBe(0.07);
    expect(chart.min).toBe(0.05);
    expect(plain(chart.axis)).toEqual(['7 %', '6 %', '5 %']);
  });

  it('binary noise does not add an extra tick below the data either', async () => {
    // 0.15 / 0.025 is 5.999999999999999: rounded down blindly the scale would start at 12,5 %.
    const chart = await renderChart({ format: 'percent', chartType: 'line' }, [
      { day: 'Mon', total: 0.15 },
      { day: 'Tue', total: 0.25 },
    ]);
    expect(chart.min).toBe(0.15);
    expect(chart.max).toBe(0.25);
    expect(plain(chart.axis)).toEqual(['25 %', '22,5 %', '20 %', '17,5 %', '15 %']);
  });
});

describe('hub#2392 — the days of a chart are written in the language of the UI', () => {
  it('ISO days become «29 sept» in Spanish and «Sep 29» in English', async () => {
    hubIn('EUR', 2);
    const rows = [
      { day: '2026-09-28', total: 100 },
      { day: '2026-09-29', total: 200 },
    ];
    const es = await renderChart({ format: 'currency' }, rows);
    expect(es.labels).toEqual(['28 sept', '29 sept']);

    i18n.global.locale.value = 'en';
    const en = await renderChart({ format: 'currency' }, rows);
    expect(en.labels).toEqual(['Sep 28', 'Sep 29']);
  });

  it('a business day is not moved to the previous day west of Greenwich', async () => {
    // `new Date('2026-09-29')` is midnight UTC — the 28th in America. The day the query returns is
    // already the business day (sales#323): it is painted as is, whatever the device's zone.
    const saved = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';
    try {
      const chart = await renderChart({}, [{ day: '2026-09-29', total: 1 }]);
      expect(chart.labels).toEqual(['29 sept']);
    } finally {
      // Assigning `undefined` to process.env stores the string "undefined", not an unset zone.
      if (saved === undefined) delete process.env.TZ;
      else process.env.TZ = saved;
    }
  });

  it('labels that are not ISO days are left as the module sends them', async () => {
    const chart = await renderChart({}, [
      { day: 'Table 1', total: 1 },
      { day: '2026-09', total: 2 },
    ]);
    expect(chart.labels).toEqual(['Table 1', '2026-09']);
  });
});

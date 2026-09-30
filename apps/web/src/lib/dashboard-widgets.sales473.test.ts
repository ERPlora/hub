// @vitest-environment happy-dom
//
// ERPlora/sales#473 (from ERPlora/outfitkit#250): with the hub in English, the «Sales, last 7 days»
// panel of the home page drew the legend of its chart as «Ventas», and the panel picker grouped the
// sales panels under «Ventas» too. The shell translated a panel's `title` and `options.label` from
// the module's locale file (`locale.widgets.<id>`), but handed `options.seriesName` and `category`
// to the board verbatim — so a module could only pick ONE language for them.
//
// Contract: the canonical (English) `seriesName` and `category` of the manifest are translated from
// `locale.widgets.<id>.seriesName` / `.category` for the active language, exactly like `title` and
// `label`; with no entry the canonical text stays. The «Recommended» preset the shell builds speaks
// the language it is handed, not a hardcoded Spanish word.
//
// The shell side of the fix is tracked in ERPlora/hub#2401; the module side in ERPlora/sales#473.
import { describe, it, expect, vi } from 'vitest';

// Same isolation as dashboard-widgets.test.ts: `module-loader` drags the `~icons/…?raw` chain that
// the vitest transform denies. Only its I/O functions are stubbed; the rows are real shapes.
vi.mock('./module-loader', () => ({
  loadInstalledManifests: vi.fn(),
  loadModuleComponent: vi.fn(),
}));

import { buildWidgetsFromManifests } from './dashboard-widgets';
import type { InstalledManifest } from './module-loader';
import type { ErploraClient } from '@erplora/module-sdk';
import type { WidgetManifestDef } from '@erplora/module-types';

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

type Chart = HTMLElement & { series?: Array<{ name?: string; data: number[] }> };

const chartDef: WidgetManifestDef = {
  title: 'Sales, last 7 days',
  kind: 'chart',
  category: 'Sales',
  query: 'sales.last_7_days',
  map: { label: 'day', value: 'total' },
  options: { chartType: 'bar', seriesName: 'Sales' },
};

const kpiDef: WidgetManifestDef = {
  title: "Today's sales",
  kind: 'kpi',
  category: 'Sales',
  default: true,
  sectors: ['retail'],
  query: 'sales.today',
  map: { value: 'total' },
};

const client = {
  query: vi.fn(async () => [{ day: '2026-09-29', total: 1200 }]),
  on: () => () => {},
} as unknown as ErploraClient;

function manifests(locale?: unknown): InstalledManifest[] {
  return [
    {
      id: 'sales',
      moduleId: 'sales',
      manifest: { id: 'sales', widgets: { 'sales.last_7_days': chartDef, 'sales.today': kpiDef } },
      locale,
    },
  ] as unknown as InstalledManifest[];
}

async function legendOf(mods: InstalledManifest[]): Promise<string | undefined> {
  const { widgets } = buildWidgetsFromManifests(mods, { client, sector: null });
  const cell = document.createElement('div');
  widgets.find((w) => w.id === 'sales.last_7_days')!.render(cell);
  await flush();
  const chart = cell.querySelector('ok-chart') as Chart | null;
  if (!chart) throw new Error('no ok-chart rendered');
  return chart.series?.[0]?.name;
}

const spanish = {
  widgets: {
    'sales.last_7_days': { title: 'Ventas últimos 7 días', category: 'Ventas', seriesName: 'Ventas' },
    'sales.today': { title: 'Ventas hoy', category: 'Ventas' },
  },
};

describe('sales#473 — the legend and the category of a panel follow the UI language', () => {
  it('🔴 the chart legend is translated from `locale.widgets.<id>.seriesName`', async () => {
    expect(await legendOf(manifests(spanish))).toBe('Ventas');
  });

  it('without a translation the legend is the canonical English of the manifest', async () => {
    expect(await legendOf(manifests())).toBe('Sales');
    expect(await legendOf(manifests({ widgets: { 'sales.last_7_days': { title: 'Ventas' } } }))).toBe('Sales');
  });

  it('🔴 the category the picker groups by is translated from `locale.widgets.<id>.category`', () => {
    const { widgets } = buildWidgetsFromManifests(manifests(spanish), { client, sector: null });
    expect(widgets.map((w) => [w.id, w.category])).toEqual([
      ['sales.last_7_days', 'Ventas'],
      ['sales.today', 'Ventas'],
    ]);
  });

  it('without a translation the category is the canonical English of the manifest', () => {
    const { widgets } = buildWidgetsFromManifests(manifests(), { client, sector: null });
    expect(widgets.map((w) => w.category)).toEqual(['Sales', 'Sales']);
  });

  // Review of hub#2417: the options were only localized when the title changed too. A panel whose
  // title reads the same in both languages («Tickets») but whose legend or caption does not would
  // have kept the English legend on a Spanish hub.
  it('translates the legend even when the title has no entry of its own', async () => {
    expect(await legendOf(manifests({ widgets: { 'sales.last_7_days': { seriesName: 'Ventas' } } }))).toBe('Ventas');
  });

  // On a `stat`: since hub#1105 a `kpi` no longer paints `options.label`, so `stat` is where the
  // translated caption can be observed (same as dashboard-widgets.test.ts).
  it('translates the caption (options.label) even when the title has no entry of its own', async () => {
    const statDef: WidgetManifestDef = { ...kpiDef, kind: 'stat', options: { label: 'Today' } };
    const mods = [
      {
        id: 'sales',
        moduleId: 'sales',
        manifest: { id: 'sales', widgets: { 'sales.today': statDef } },
        locale: { widgets: { 'sales.today': { label: 'Hoy' } } },
      },
    ] as unknown as InstalledManifest[];
    const { widgets } = buildWidgetsFromManifests(mods, { client, sector: null });
    const cell = document.createElement('div');
    document.body.appendChild(cell);
    widgets[0]!.render(cell);
    await flush();
    expect((cell.querySelector('ok-stat') as (HTMLElement & { label?: string }) | null)?.label).toBe('Hoy');
    document.body.replaceChildren();
  });

  it('translating the legend keeps the rest of the chart options (format, chart type)', async () => {
    const mods = manifests(spanish);
    const { widgets } = buildWidgetsFromManifests(mods, { client, sector: null });
    const cell = document.createElement('div');
    widgets.find((w) => w.id === 'sales.last_7_days')!.render(cell);
    await flush();
    const chart = cell.querySelector('ok-chart') as (Chart & { type?: string }) | null;
    expect(chart?.type).toBe('bar');
    expect(chart?.series?.[0]?.data).toEqual([1200]);
  });

  it('🔴 the «Recommended» preset is labelled with the text the shell hands in', () => {
    const { presets } = buildWidgetsFromManifests(manifests(), {
      client,
      sector: 'retail',
      labels: { recommended: 'Recommended' },
    });
    expect(presets.map((p) => [p.id, p.label])).toEqual([['recommended', 'Recommended']]);
  });
});

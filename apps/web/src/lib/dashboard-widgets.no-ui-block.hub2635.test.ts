// @vitest-environment happy-dom
//
// hub#2635: a module may declare `widgets` without a `ui` block — the install gate does not ask for
// one. Installing such a module emptied the WHOLE home board: `loadInstalledManifests` read
// `manifest.ui.entry` unconditionally, the TypeError rejected the collection of every module, and
// the board's `catch` degraded to «Panel vacío» with no error anywhere. The menu had the same read
// (`loadMenu`), so one such module also took every other app out of the launcher.
//
// Contract: one ill-declared module cannot take the others down. Its declarative panels still
// render (they need no bundle); a panel that mounts its component shows the panel error state
// instead of importing a bundle that does not exist; and the menu leaves it out, like a module whose
// manifest cannot be read.
//
// Real `module-loader` and real `dashboard-widgets`: only the network and the icon registry are
// stubbed, so the TypeError of the bug is what turns these tests red.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));
vi.mock('./icons', () => ({ moduleIconRegistry: (i: Record<string, string>) => i }));
vi.mock('ionicons', () => ({ addIcons: () => {} }));
vi.mock('./entitlement', () => ({ isModuleEntitled: () => true }));

import type { ErploraClient } from '@erplora/module-sdk';
import { collectDashboardWidgets } from './dashboard-widgets';
import { invalidateManifestCache, loadInstalledManifests, loadMenu } from './module-loader';

function navItem(moduleId: string) {
  return {
    module_id: moduleId,
    module_name: moduleId,
    id: `${moduleId}-main`,
    label: moduleId,
    icon: null,
    component: `erp-${moduleId}`,
    module_version: '1.0.0',
  };
}

const salesManifest = {
  id: 'sales',
  name: 'Sales',
  version: '1.0.0',
  ui: { entry: 'dist/sales.esm.js' },
  widgets: {
    'sales.today': { title: 'Sales today', kind: 'kpi', query: 'sales.today', map: { value: 'total' } },
  },
};

/** Widgets declared, `ui` block missing — what the install gate lets through today. */
const noUiManifest = {
  id: 'noui',
  name: 'No UI',
  version: '1.0.0',
  widgets: {
    'noui.count': { title: 'Open tickets', kind: 'kpi', query: 'noui.count', map: { value: 'n' } },
    'noui.card': { title: 'Ticket card', component: 'erp-noui-card' },
  },
};

const imported: string[] = [];

function stubFetch(manifests: Record<string, unknown>): void {
  const navData = Object.keys(manifests).map(navItem);
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.startsWith('/api/navigation')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, data: navData, active_modules: navData.length }),
        } as unknown as Response;
      }
      const match = /^\/modules\/([^/]+)(?:\/v\/[^/]+)?\/module\.json$/.exec(url);
      if (match && manifests[match[1]]) {
        return { ok: true, status: 200, json: async () => manifests[match[1]] } as unknown as Response;
      }
      if (url.endsWith('.js')) imported.push(url);
      return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
    }),
  );
}

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0));
const client = {
  query: vi.fn(async () => [{ total: 1200, n: 3 }]),
  on: () => () => {},
  forModule: () => client,
} as unknown as ErploraClient;

beforeEach(() => {
  vi.unstubAllGlobals();
  invalidateManifestCache();
  imported.length = 0;
});

describe('hub#2635 — a module with widgets and no `ui` block', () => {
  it('does not empty the board: every other module keeps its panels', async () => {
    stubFetch({ sales: salesManifest, noui: noUiManifest });

    const { widgets } = await collectDashboardWidgets({ client, sector: null });

    expect(widgets.map((w) => w.id)).toEqual(expect.arrayContaining(['sales.today', 'noui.count', 'noui.card']));
  });

  it('is collected without a bundle url, and the modules around it keep theirs', async () => {
    stubFetch({ sales: salesManifest, noui: noUiManifest });

    const mods = await loadInstalledManifests();

    expect(mods.map((m) => m.moduleId)).toEqual(['sales', 'noui']);
    expect(mods.find((m) => m.moduleId === 'sales')?.entryUrl).toBe('/modules/sales/v/1.0.0/dist/sales.esm.js');
    expect(mods.find((m) => m.moduleId === 'noui')?.entryUrl).toBeNull();
  });

  it('still renders its declarative panel with its data', async () => {
    stubFetch({ sales: salesManifest, noui: noUiManifest });
    const { widgets } = await collectDashboardWidgets({
      client,
      sector: null,
      labels: { error: 'Not available' },
    });

    const cell = document.createElement('div');
    widgets.find((w) => w.id === 'noui.count')!.render(cell);
    await flush();

    // The renderers write by PROPERTY (`ok-kpi.value`, `ok-empty-state.message`), not as text.
    const kpi = cell.querySelector('ok-kpi') as (HTMLElement & { value?: string }) | null;
    expect(kpi?.value).toBe('3');
    expect(cell.querySelector('ok-empty-state')).toBeNull();
  });

  it('shows the panel error state for its component panel and imports nothing', async () => {
    stubFetch({ sales: salesManifest, noui: noUiManifest });
    const { widgets } = await collectDashboardWidgets({
      client,
      sector: null,
      labels: { error: 'Not available' },
    });

    const cell = document.createElement('div');
    document.body.appendChild(cell);
    widgets.find((w) => w.id === 'noui.card')!.render(cell);
    await flush();
    await flush();

    const error = cell.querySelector('ok-empty-state') as (HTMLElement & { message?: string }) | null;
    expect(error?.message).toBe('Not available');
    expect(cell.querySelector('erp-noui-card')).toBeNull();
    expect(imported.filter((u) => u.includes('/noui/'))).toEqual([]);
    cell.remove();
  });

  it('is left out of the menu without taking the other apps with it', async () => {
    stubFetch({ sales: salesManifest, noui: noUiManifest });

    const entries = await loadMenu();

    expect(entries.map((e) => e.moduleId)).toEqual(['sales']);
  });
});

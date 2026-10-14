// The sale app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';
import { SALE_TABS } from './tabs';

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

const PAGES: Record<string, () => Promise<{ default: RouteComponent }>> = {
  '/sale/pos': () => import('./pages/PosPage.vue'),
  '/sale/sales': () => import('./pages/SalesPage.vue'),
  '/sale/quick-notes': () => import('./pages/QuickNotesPage.vue'),
  '/sale/departments': () => import('./pages/DepartmentsPage.vue'),
  '/sale/settings': () => import('./pages/SettingsPage.vue'),
};

describe('sale routes.ts', () => {
  it('maps every section of the menu (the tabs, apps.py) to its page, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual(SALE_TABS.map((tab) => [tab.to, true]));
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) {
      expect(typeof r.component).toBe('function');
      expect(await load(r)).toBe((await PAGES[r.path]()).default);
    }
    // Transforming the pages with their sheets takes a while when the whole suite runs at once.
  }, 60_000);

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});

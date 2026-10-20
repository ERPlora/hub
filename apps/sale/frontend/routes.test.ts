// The sale app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';
import { SALE_TABS } from './tabs';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine. A real page where a stub is expected is a page
// this file does not stub.
vi.mock('./pages/PosPage.vue', () => ({ default: { name: 'PosPage' } }));
vi.mock('./pages/SalesPage.vue', () => ({ default: { name: 'SalesPage' } }));
vi.mock('./pages/QuickNotesPage.vue', () => ({ default: { name: 'QuickNotesPage' } }));
vi.mock('./pages/DepartmentsPage.vue', () => ({ default: { name: 'DepartmentsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

/** Path → its page. */
const PAGES: Record<string, string> = {
  '/sale/pos': 'PosPage',
  '/sale/sales': 'SalesPage',
  '/sale/quick-notes': 'QuickNotesPage',
  '/sale/departments': 'DepartmentsPage',
  '/sale/settings': 'SettingsPage',
};

describe('sale routes.ts', () => {
  it('maps every section of the menu (the tabs, apps.py) to its page, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual(SALE_TABS.map((tab) => [tab.to, true]));
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) {
      expect(typeof r.component).toBe('function');
      expect(await load(r), r.path).toEqual({ name: PAGES[r.path] });
    }
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});

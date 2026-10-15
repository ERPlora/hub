// The service app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';
import { SERVICE_TABS } from './tabs';

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('service routes.ts', () => {
  it('maps Services, Categories, Packages and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/service/services', true],
      ['/service/categories', true],
      ['/service/packages', true],
      ['/service/settings', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', { timeout: 60_000 }, async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    const pages = await Promise.all(routes.map(load));
    expect(pages).toEqual([
      (await import('./pages/ServicesPage.vue')).default,
      (await import('./pages/CategoriesPage.vue')).default,
      (await import('./pages/PackagesPage.vue')).default,
      (await import('./pages/SettingsPage.vue')).default,
    ]);
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for every tab, and every menu entry of apps.py is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(SERVICE_TABS.map((tab) => tab.to));
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/service\/[a-z-]+)"/g)].map((m) => m[1]);
    expect(paths.every((path) => routes.some((r) => r.path === path))).toBe(true);
    expect(paths).toHaveLength(3);
  });
});

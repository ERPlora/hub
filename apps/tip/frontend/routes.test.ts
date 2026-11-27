// The tips app's `routes.ts`: the list of tips, the report, the settings and my tips → their pages, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand (their own tests
// mount them).
vi.mock('./pages/TipsPage.vue', () => ({ default: { name: 'TipsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));
vi.mock('./pages/ReportPage.vue', () => ({ default: { name: 'ReportPage' } }));
vi.mock('./pages/MyTipsPage.vue', () => ({ default: { name: 'MyTipsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('tips routes.ts', () => {
  it('maps the tips, the report, the settings and my tips, behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/tip/tips', true],
      ['/tip/report', true],
      ['/tip/settings', true],
      ['/tip/mine', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toEqual({ name: 'TipsPage' });
    expect(await load(routes[1])).toEqual({ name: 'ReportPage' });
    expect(await load(routes[2])).toEqual({ name: 'SettingsPage' });
    expect(await load(routes[3])).toEqual({ name: 'MyTipsPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for every path of its menu in apps.py', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...new Set([...appsPy.matchAll(/"(\/tip\/[a-z_]+)"/g)].map((m) => m[1]))];
    expect(paths).toEqual(['/tip/tips', '/tip/report', '/tip/settings', '/tip/mine']);
    for (const path of paths) expect(routes.some((r) => r.path === path), path).toBe(true);
  });
});

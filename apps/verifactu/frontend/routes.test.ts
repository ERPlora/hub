// The verifactu app's `routes.ts`: its six sections and the detail of a record → their pages, behind a session, and
// nothing else (main.ts reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('verifactu routes.ts', () => {
  it('maps Records, a record, Contingency, Events, Recovery, Configuration and Settings, behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth, r.props ?? false])).toEqual([
      ['/verifactu/records', true, false],
      ['/verifactu/records/:id', true, true],
      ['/verifactu/contingency', true, false],
      ['/verifactu/events', true, false],
      ['/verifactu/recovery', true, false],
      ['/verifactu/config', true, false],
      ['/verifactu/settings', true, false],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    const pages = ['RecordsPage', 'RecordDetailPage', 'ContingencyPage', 'EventsPage', 'RecoveryPage', 'ConfigPage', 'SettingsPage'];
    for (const [index, page] of pages.entries()) {
      expect(await load(routes[index])).toBe((await import(`./pages/${page}.vue`)).default);
    }
  }, 30_000);

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for every entry of the navigation of apps.py', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/verifactu\/[a-z]+)"/g)].map((m) => m[1]);
    expect(paths).toEqual(['/verifactu/records', '/verifactu/contingency', '/verifactu/events', '/verifactu/recovery', '/verifactu/config', '/verifactu/settings']);
    for (const path of paths) expect(routes.some((r) => r.path === path), path).toBe(true);
  });
});

// The online booking app's `routes.ts`: routes → pages and nothing else (main.ts reads the default export).
// The old module's two sections (Bookings, Settings: apps.py `navigation`) and, on the dev server only, the
// preview of the public booking page.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, 'routes.ts'), 'utf8');
const APPS_PY = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');

function route(path: string): RouteRecordRaw {
  const found = routes.find((r) => r.path === path);
  if (!found) throw new Error(`no route ${path}`);
  return found;
}

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('online booking routes.ts', () => {
  it('maps the inbox and the settings behind a session (and the preview in dev)', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/online_booking/bookings', true],
      ['/online_booking/settings', true],
      ['/online_booking/preview', true],
    ]);
  });

  it('every menu entry of apps.py has its page', () => {
    const menu = [...APPS_PY.matchAll(/"(\/online_booking\/[^"]+)"/g)].map((m) => m[1]);
    expect(menu).toEqual(['/online_booking/bookings', '/online_booking/settings']);
    for (const path of menu) expect(routes.some((r) => r.path === path), path).toBe(true);
  });

  it('offers the preview only on the dev server', () => {
    expect(SOURCE).toMatch(/import\.meta\.env\.DEV\s*\?/);
  });

  it('loads each page on demand (one chunk per page), not at boot', { timeout: 30_000 }, async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(route('/online_booking/bookings'))).toBe((await import('./pages/BookingsPage.vue')).default);
    expect(await load(route('/online_booking/settings'))).toBe((await import('./pages/SettingsPage.vue')).default);
    expect(await load(route('/online_booking/preview'))).toBe((await import('./pages/PreviewPage.vue')).default);
  });

  it('imports types only at the top, so main.ts can glob it before the shell boots', () => {
    const imports = [...SOURCE.matchAll(/^import .*$/gm)].map((m) => m[0]);
    expect(imports.every((line) => line.startsWith('import type'))).toBe(true);
  });
});

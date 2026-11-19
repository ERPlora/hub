// The online booking app's `routes.ts`: routes → pages and nothing else (main.ts reads the default export).
// The old module's two sections (Bookings, Settings: apps.py `navigation`), the booking page base's public door serves
// without a session (`/p/<slug>/book`, and `/p/<slug>/book/<token>` for a customer's personal link) and, on the dev
// server only, its preview.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine. A real page where a stub is expected is a page
// this file does not stub.
vi.mock('./pages/BookingsPage.vue', () => ({ default: { name: 'BookingsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));
vi.mock('./pages/PreviewPage.vue', () => ({ default: { name: 'PreviewPage' } }));
vi.mock('./pages/PublicBookingPage.vue', () => ({ default: { name: 'PublicBookingPage' } }));

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
  it('maps the inbox and the settings behind a session, the public page without one (and the preview in dev)', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/online_booking/bookings', true],
      ['/online_booking/settings', true],
      ['/p/:slug/book', false],
      ['/p/:slug/book/:token', false],
      ['/online_booking/preview', true],
    ]);
  });

  it('paints the public page without the shell\'s menus: a customer is no member of the team', () => {
    expect(route('/p/:slug/book').meta?.chrome).toBe(false);
    expect(route('/p/:slug/book/:token').meta?.chrome).toBe(false);
  });

  it('serves the public page on the path base names for it (apps.py `public_pages`)', () => {
    const [, page] = /public_pages = \{"([^"]+)"/.exec(APPS_PY) ?? [];
    expect(route('/p/:slug/book').path).toBe(`/p/:slug/${page}`);
    expect(route('/p/:slug/book/:token').path).toBe(`/p/:slug/${page}/:token`);
  });

  it('every menu entry of apps.py has its page', () => {
    const menu = [...APPS_PY.matchAll(/"(\/online_booking\/[^"]+)"/g)].map((m) => m[1]);
    expect(menu).toEqual(['/online_booking/bookings', '/online_booking/settings']);
    for (const path of menu) expect(routes.some((r) => r.path === path), path).toBe(true);
  });

  it('offers the preview only on the dev server', () => {
    expect(SOURCE).toMatch(/import\.meta\.env\.DEV\s*\?/);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(route('/online_booking/bookings'))).toEqual({ name: 'BookingsPage' });
    expect(await load(route('/online_booking/settings'))).toEqual({ name: 'SettingsPage' });
    expect(await load(route('/online_booking/preview'))).toEqual({ name: 'PreviewPage' });
    expect(await load(route('/p/:slug/book'))).toEqual({ name: 'PublicBookingPage' });
    expect(await load(route('/p/:slug/book/:token'))).toEqual({ name: 'PublicBookingPage' });
  });

  it('imports types only at the top, so main.ts can glob it before the shell boots', () => {
    const imports = [...SOURCE.matchAll(/^import .*$/gm)].map((m) => m[0]);
    expect(imports.every((line) => line.startsWith('import type'))).toBe(true);
  });
});

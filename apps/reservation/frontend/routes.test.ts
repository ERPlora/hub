// The reservation app's `routes.ts`: its three sections and Settings → their pages, behind a session, and
// nothing else (main.ts reads the default export; menu, permissions and active apps come from the server).
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
vi.mock('./pages/ReservationsPage.vue', () => ({ default: { name: 'ReservationsPage' } }));
vi.mock('./pages/WaitlistPage.vue', () => ({ default: { name: 'WaitlistPage' } }));
vi.mock('./pages/AvailabilityPage.vue', () => ({ default: { name: 'AvailabilityPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('reservation routes.ts', () => {
  it('maps Reservations, Waitlist, Availability and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/reservation/reservations', true],
      ['/reservation/waitlist', true],
      ['/reservation/availability', true],
      ['/reservation/settings', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toEqual({ name: 'ReservationsPage' });
    expect(await load(routes[1])).toEqual({ name: 'WaitlistPage' });
    expect(await load(routes[2])).toEqual({ name: 'AvailabilityPage' });
    expect(await load(routes[3])).toEqual({ name: 'SettingsPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('serves every menu entry of apps.py, plus Settings (a tab of the pages)', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/reservation\/[a-z]+)"/g)].map((m) => m[1]);
    expect(paths).toEqual(routes.map((r) => r.path).filter((path) => path !== '/reservation/settings'));
  });
});

// The attendance app's `routes.ts`: Clock in, Records and Settings → their pages, behind a session, and
// nothing else (main.ts reads the default export; menu, permissions and active apps come from the server).
// The op → route map of the SDK knows every attendance operation that has a route (api.py).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine. A real page where a stub is expected is a page
// this file does not stub.
vi.mock('./pages/ClockPage.vue', () => ({ default: { name: 'ClockPage' } }));
vi.mock('./pages/RecordsPage.vue', () => ({ default: { name: 'RecordsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('attendance routes.ts', () => {
  it('maps Clock in, Records and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/attendance/clock', true],
      ['/attendance/records', true],
      ['/attendance/settings', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toEqual({ name: 'ClockPage' });
    expect(await load(routes[1])).toEqual({ name: 'RecordsPage' });
    expect(await load(routes[2])).toEqual({ name: 'SettingsPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('matches the navigation of apps.py (and the settings tab)', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/attendance\/[a-z]+)"/g)].map((m) => m[1]);
    expect([...paths, '/attendance/settings']).toEqual(routes.map((r) => r.path));
  });

  it('binds the fourteen routed operations to apps/attendance/api.py: queries by GET, commands by POST', () => {
    const attendance = Object.fromEntries(Object.entries(OPERATION_ROUTES).filter(([op]) => op.startsWith('attendance.')));
    expect(attendance).toEqual({
      'attendance.record.current': { method: 'get', path: '/api/attendance/current' },
      'attendance.record.list': { method: 'get', path: '/api/attendance/records' },
      'attendance.record.detail': { method: 'get', path: '/api/attendance/records/detail' },
      'attendance.record.export': { method: 'get', path: '/api/attendance/records/export' },
      'attendance.record.correct': { method: 'post', path: '/api/attendance/records/correct' },
      'attendance.record.clock_in': { method: 'post', path: '/api/attendance/clock_in' },
      'attendance.record.clock_out': { method: 'post', path: '/api/attendance/clock_out' },
      'attendance.break.start': { method: 'post', path: '/api/attendance/breaks/start' },
      'attendance.break.end': { method: 'post', path: '/api/attendance/breaks/end' },
      'attendance.correction.list': { method: 'get', path: '/api/attendance/corrections' },
      'attendance.presence.list': { method: 'get', path: '/api/attendance/presence' },
      'attendance.person.list': { method: 'get', path: '/api/attendance/people' },
      'attendance.settings.get': { method: 'get', path: '/api/attendance/settings' },
      'attendance.settings.update': { method: 'post', path: '/api/attendance/settings' },
    });
  });
});

// Online orders' `routes.ts`: its one screen, the tables' QR codes, behind a session and loaded on demand, on the path
// of its menu entry in apps.py; nothing else (main.ts reads the default export; menu, permissions and active apps come
// from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import { appMenu } from '../../../base/frontend/__tests__/app-menu';
import routes from './routes';

// The page, stubbed: this file checks which page the route loads, not the page (its own test mounts it).
vi.mock('./pages/QrCodesPage.vue', () => ({ default: { name: 'QrCodesPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

describe('online_order routes.ts', () => {
  it('maps the tables’ QR codes behind a session, loaded on demand', async () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([['/online_order/qr-codes', true]]);
    const loader = routes[0].component as () => Promise<{ default: RouteComponent }>;
    expect(typeof loader).toBe('function');
    expect((await loader()).default).toEqual({ name: 'QrCodesPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('every menu entry of apps.py has its page, opened by whoever may see the codes', () => {
    expect(appMenu('online_order').map((entry) => [entry.path, entry.permission])).toEqual([
      ['/online_order/qr-codes', 'online_order.view_qr_code'],
    ]);
    for (const entry of appMenu('online_order')) expect(routes.some((r) => r.path === entry.path), entry.path).toBe(true);
  });
});

// base's Files at `/files` (APP-BASE-8; the old hub's address, the side menu's «Files» entry): one route, its folder in
// the query (`?folder=Facturas/2026`), its page loaded on demand.
import type { RouteComponent } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

vi.mock('./pages/FilesPage.vue', () => ({ default: { name: 'FilesPage' } }));

describe('base routes · Files', () => {
  it('serves Files at the old hub’s `/files`, for a session, loaded on demand', async () => {
    const route = routes.find((r) => r.path === '/files');
    expect([route?.name, route?.meta?.auth]).toEqual(['base-files', true]);
    const loader = route?.component as () => Promise<{ default: RouteComponent }>;
    expect(((await loader()).default as { name: string }).name).toBe('FilesPage');
  });
});

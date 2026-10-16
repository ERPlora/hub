// The WhatsApp inbox's `routes.ts`: its two sections → their pages, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
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

describe('whatsapp_inbox routes.ts', () => {
  it('maps Inbox and Settings (the paths of the menu in apps.py), both behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/whatsapp_inbox/inbox', true],
      ['/whatsapp_inbox/settings', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toBe((await import('./pages/InboxPage.vue')).default);
    expect(await load(routes[1])).toBe((await import('./pages/SettingsPage.vue')).default);
  }, 30_000);

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('matches the navigation of apps.py, entry for entry', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/whatsapp_inbox\/[a-z]+)"/g)].map((m) => m[1]);
    expect(paths).toEqual(routes.map((r) => r.path));
  });
});

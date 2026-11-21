// What main.ts boots with on import, from base's and the apps' own files: the routes and catalogues Vite globs, the
// shared assistant's words and base's pieces of the chrome; and the rule that keeps each catalogue under its own key.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async () => (await import('./__tests__/main-boot')).shellModule());
vi.mock('@erplora/ui/sdk', async (importOriginal) => (await import('./__tests__/main-boot')).sdkModule(importOriginal));
// The reload of a hub that stopped serving the page (base/frontend/lib/change-business.test.ts runs it).
const gone = vi.hoisted(() => ({ reloadOrForgetGone: vi.fn(async () => {}) }));
vi.mock('../base/frontend/lib/change-business', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../base/frontend/lib/change-business')>()),
  reloadOrForgetGone: gone.reloadOrForgetGone,
}));

import { createShell } from '@erplora/ui/shell';
import { createLiveClient } from '@erplora/ui/sdk';

import { embedPage, shellFakes } from './__tests__/main-boot';

const HERE = dirname(fileURLToPath(import.meta.url));

// Imported with the file, out of any test's or hook's clock (main.chrome.test.ts says why).
const { app, router } = shellFakes();
embedPage();
vi.mocked(createShell).mockResolvedValue({ app, router } as never);
await import('./main');
const importBoot = vi.mocked(createShell).mock.calls[0][0];

describe('main.ts', () => {
  it('boots on import with the routes Vite globs from apps/*/frontend/routes.ts (the demo pages among them)', () => {
    const routes = importBoot.routes as RouteRecordRaw[];
    expect(routes.map((r) => r.path)).toEqual(expect.arrayContaining(['/demo/items', '/demo/items/:id']));
  });

  it("boots with base's Home at `/`: its route goes before the shell's grid, under a name of its own", () => {
    const routes = importBoot.routes as RouteRecordRaw[];
    const home = routes.filter((r) => r.path === '/');
    expect(home.map((r) => [r.name, r.meta?.auth])).toEqual([['base-home', true]]);
    // The shell's grid (`home: true`) stays registered after it, as the fallback of `/` and «Home» first in the menu.
    expect(importBoot.home).toBe(true);
  });

  it("plugs base's pieces into the chrome: the assistant in the topbar, «Upgrade plan» and «Manage on erplora.com» at the menu's foot, and the device's notices and the assistant's panel beside the pane", async () => {
    const chrome = importBoot.chrome as Record<string, unknown>;
    expect(Object.keys(chrome).sort()).toEqual(['background', 'sidebarFooter', 'topbar']);
    for (const piece of Object.values(chrome)) expect(piece).toBeTruthy();
    // Loaded on demand; what each one loads.
    const loaded = async (piece: unknown) =>
      ((await (piece as { __asyncLoader: () => Promise<{ __name?: string }> }).__asyncLoader()) ?? {}).__name;
    expect([await loaded(chrome.topbar), await loaded(chrome.sidebarFooter), await loaded(chrome.background)]).toEqual([
      'TopbarChrome',
      'SidebarFooter',
      'BackgroundChrome',
    ]);
  });

  it('boots with a live client that, when the hub stops serving the page, first checks whether it is gone (HUB_APP-F05)', () => {
    const overrides = vi.mocked(createLiveClient).mock.calls[0][1]!;
    expect(gone.reloadOrForgetGone).not.toHaveBeenCalled();

    overrides.reload!();

    expect(gone.reloadOrForgetGone).toHaveBeenCalledOnce();
  });

  it("on import, globs base's catalogue next to the apps' (the Home would show raw keys otherwise)", () => {
    const messages = importBoot.messages as Record<string, { base: { home: { title: string } } }>;
    expect([messages.en.base.home.title, messages.es.base.home.title]).toEqual(['Home', 'Inicio']);
  });

  it("on import, the shell speaks the shared assistant's words next to base's (its panel would show raw keys otherwise)", () => {
    const messages = importBoot.messages as Record<string, { assistant: { send: string }; base: { assistant: { empty: string } } }>;
    expect([messages.en.assistant.send, messages.es.assistant.send]).toEqual(['Send', 'Enviar']);
    expect(messages.es.base.assistant.empty).toBe('Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.');
  });

  it('on import, globs the real app catalogues (the demo pages would show raw keys otherwise)', () => {
    const messages = importBoot.messages as Record<string, { demo: { items: { title: string } } }>;
    expect([messages.en.demo.items.title, messages.es.demo.items.title]).toEqual(['Demo items', 'Elementos']);
  });
});

describe('app catalogue guards', () => {
  it('keeps base/frontend/locale/<lang>.json under base and every apps/<id>/frontend/locale/<lang>.json under its own <id>, so merging apps never collides', () => {
    const appsDir = join(HERE, '..', 'apps');
    const baseLocale = join(HERE, '..', 'base', 'frontend', 'locale');
    const catalogues = readdirSync(appsDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && existsSync(join(appsDir, entry.name, 'frontend', 'locale')))
      .flatMap((entry) => {
        const dir = join(appsDir, entry.name, 'frontend', 'locale');
        return readdirSync(dir)
          .filter((name) => name.endsWith('.json'))
          .map((name) => ({ app: entry.name, file: join(dir, name) }));
      })
      .concat(
        (existsSync(baseLocale) ? readdirSync(baseLocale) : [])
          .filter((name) => name.endsWith('.json'))
          .map((name) => ({ app: 'base', file: join(baseLocale, name) })),
      );
    expect(catalogues.map(({ app }) => app)).toContain('base');
    for (const { app, file } of catalogues) {
      expect(Object.keys(JSON.parse(readFileSync(file, 'utf8')) as object), file).toEqual([app]);
    }
  });
});

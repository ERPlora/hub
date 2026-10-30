// The Vite config is a contract with Django (`packages/live/live/spa.py` and `LIVE["spa"]` in
// `config/settings.py`): the dev server URLs and the manifest Django reads come from here.
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { PluginOption } from 'vite';
import { afterEach, describe, expect, it, vi } from 'vitest';

import config from './vite.config';

const HUB_DIR = dirname(fileURLToPath(import.meta.url));

function pluginNames(options: PluginOption[] | undefined): string[] {
  return (options ?? []).flat(Infinity as 1).flatMap((p) => (p && 'name' in p ? [p.name] : []));
}

describe('vite.config', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('serves from the hub-next directory under /static/spa/ (dev and build alike)', () => {
    expect(config.root).toBe(HUB_DIR);
    expect(config.base).toBe('/static/spa/');
  });

  it('uses the shared ERPlora plugins (Vue, baked icons, Tailwind, defines)', () => {
    expect(pluginNames(config.plugins)).toEqual(expect.arrayContaining(['vite:vue', 'unplugin-icons', 'erplora:defines']));
  });

  it('builds frontend/main.ts and frontend/website.ts into frontend/dist with the manifest Django reads', () => {
    const build = config.build ?? {};
    expect(build.outDir).toBe('frontend/dist');
    expect(build.emptyOutDir).toBe(true);
    // settings.LIVE["spa"]["manifest"] = SPA_DIST / ".vite" / "manifest.json"
    expect(build.manifest).toBe('.vite/manifest.json');
    expect(build.target).toBe('es2022');
    // The manifest keys are these paths: settings.LIVE["spa"]["entry"] = "frontend/main.ts" (the SPA), and
    // {% hub_assets "frontend/website.ts" %} (base/templatetags/hub_assets.py) for a hub's public website.
    expect(build.rollupOptions?.input).toEqual({ main: 'frontend/main.ts', website: 'frontend/website.ts' });
  });

  it('runs the dev server on localhost:5173 only, with absolute asset URLs and HMR there', async () => {
    // live/spa.py points DEBUG pages at http://localhost:5173/static/spa/{@vite/client,frontend/main.ts}.
    // Without VITE_DEV_PORT, whatever the shell exports (the e2e recipe of parallel stacks exports it).
    vi.stubEnv('VITE_DEV_PORT', undefined);
    vi.resetModules();
    const { default: unmoved } = await import('./vite.config');
    expect(unmoved.server).toMatchObject({
      host: 'localhost',
      port: 5173,
      strictPort: true,
      origin: 'http://localhost:5173',
      hmr: { host: 'localhost', port: 5173 },
    });
  });

  describe('VITE_DEV_PORT (a second checkout beside another runserver, as the e2e of a branch)', () => {
    it('moves the dev server, its asset URLs and HMR to that port, the one Django reads too', async () => {
      vi.stubEnv('VITE_DEV_PORT', '5183');
      vi.resetModules();
      const { default: moved } = await import('./vite.config');
      expect(moved.server).toMatchObject({
        host: 'localhost',
        port: 5183,
        strictPort: true,
        origin: 'http://localhost:5183',
        hmr: { host: 'localhost', port: 5183 },
      });
    });

    it('refuses a value that is no TCP port', async () => {
      vi.stubEnv('VITE_DEV_PORT', '70000');
      vi.resetModules();
      await expect(import('./vite.config')).rejects.toThrow(/VITE_DEV_PORT/);
    });
  });

  it('tests the shell entry and every app frontend in happy-dom', () => {
    expect(config.test?.environment).toBe('happy-dom');
    expect(config.test?.include).toEqual(
      expect.arrayContaining(['frontend/**/*.test.ts', 'base/frontend/**/*.test.ts', 'apps/*/frontend/**/*.test.ts', 'vite.config.test.ts']),
    );
    // Vitest's default `exclude` drops every `vite.config.*`, this test included.
    expect(config.test?.exclude).toEqual(['**/node_modules/**', '**/dist/**']);
  });

  it('runs the hub setup before every test file: no real timer outlives a test, and the assistant is the Hub\'s', () => {
    // As packages/ui's; proven by its own test (vitest.setup.test.ts), which the suite collects. The assistant's, a
    // file of base's tests (its type project is the tests', not the root config's).
    expect(config.test?.setupFiles).toEqual(['./vitest.setup.ts', './base/frontend/__tests__/assistant.setup.ts']);
    expect(config.test?.include).toEqual(expect.arrayContaining(['vitest.setup.test.ts']));
  });
});

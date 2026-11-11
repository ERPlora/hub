// @vitest-environment node
// The Vite config is a contract with Django (`packages/live/live/spa.py` and `LIVE["spa"]` in
// `config/settings.py`): the dev server URLs and the manifest Django reads come from here. In Node, where the config
// runs: under happy-dom a stand-in for `node:os` never reaches the config's own import of it.
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

  it('lets a page on a business\'s own domain of the e2e (*.test) load the dev bundle, and no other site', () => {
    const origins = (config.server?.cors as { origin: RegExp[] }).origin;
    const allowed = (origin: string): boolean => origins.some((rule) => rule.test(origin));
    expect(allowed('http://www.minegocio.test:21950')).toBe(true);
    expect(allowed('http://a.localhost:8000')).toBe(true);
    expect(allowed('http://127.0.0.1:8000')).toBe(true);
    expect(allowed('https://www.minegocio.es')).toBe(false);
    expect(allowed('http://www.minegocio.test.example.com')).toBe(false);
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

  it('runs the hub setup before every test file: no real timer outlives a test', () => {
    // As packages/ui's; proven by its own test (vitest.setup.test.ts), which the suite collects.
    expect(config.test?.setupFiles).toEqual(['./vitest.setup.ts']);
    expect(config.test?.include).toEqual(expect.arrayContaining(['vitest.setup.test.ts']));
  });

  // hub#765: on a loaded machine a test that reads files or imports a module cold runs many times slower, and fell
  // red at the fixed 5 s with nothing broken. A test that really hangs still fails: vitest.setup.test.ts proves it.
  describe('the time budgets, read from the machine when the run starts (hub#765)', () => {
    async function configOn(load: number[], cores: number) {
      vi.doMock('node:os', async (importOriginal) => ({
        ...(await importOriginal<typeof import('node:os')>()),
        loadavg: () => load,
        availableParallelism: () => cores,
      }));
      vi.resetModules();
      try {
        return (await import('./vite.config')).default;
      } finally {
        vi.doUnmock('node:os');
      }
    }

    it('are Vitest\'s own on an idle machine: 5 s a test, 10 s a hook, 1 s an expect.poll', async () => {
      const idle = await configOn([2, 1, 1], 15);
      expect(idle.test).toMatchObject({ testTimeout: 5_000, hookTimeout: 10_000, expect: { poll: { timeout: 1_000 } } });
      expect(idle.test?.provide).toEqual({ loadScale: 1 });
    });

    it('stretch with the load: at 60 over 15 cores, eight times as long, and the setup is told the same scale', async () => {
      const loaded = await configOn([60, 30, 10], 15);
      expect(loaded.test).toMatchObject({ testTimeout: 40_000, hookTimeout: 80_000, expect: { poll: { timeout: 8_000 } } });
      expect(loaded.test?.provide).toEqual({ loadScale: 8 });
    });

    it('collects the test of its own scale', () => {
      expect(config.test?.include).toEqual(expect.arrayContaining(['vitest.load.test.ts']));
    });
  });
});

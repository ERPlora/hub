// hub#787: two dev benches could not coexist — the Vite port (5173 + strictPort) and the
// /api + /ws proxy target (:8787) were hardcoded, so a second bench (worktree) died on a busy
// port. These tests pin the contract: the port and the runtime target come from the environment
// (VITE_PORT, VITE_RUNTIME_TARGET, or derived from HUB_BIND), with today's values as defaults.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const ENV_KEYS = ['VITE_PORT', 'VITE_RUNTIME_TARGET', 'HUB_BIND'] as const;
let saved: Record<string, string | undefined>;

beforeEach(() => {
  saved = {};
  for (const k of ENV_KEYS) {
    saved[k] = process.env[k];
    delete process.env[k];
  }
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

// The config reads the env at module evaluation → re-import fresh each time.
async function loadConfig() {
  vi.resetModules();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (await import('./vite.config.ts')).default as any;
}

describe('vite.config server env overrides (hub#787)', () => {
  it('defaults are unchanged: port 5173, proxy → http://127.0.0.1:8787', async () => {
    const cfg = await loadConfig();
    expect(cfg.server.port).toBe(5173);
    expect(cfg.server.strictPort).toBe(true);
    expect(cfg.server.proxy['/api'].target).toBe('http://127.0.0.1:8787');
    expect(cfg.server.proxy['/ws'].target).toBe('http://127.0.0.1:8787');
  });

  it('VITE_PORT overrides the dev server port', async () => {
    process.env.VITE_PORT = '5599';
    const cfg = await loadConfig();
    expect(cfg.server.port).toBe(5599);
  });

  it('VITE_RUNTIME_TARGET overrides the /api and /ws proxy target', async () => {
    process.env.VITE_RUNTIME_TARGET = 'http://127.0.0.1:9911';
    const cfg = await loadConfig();
    expect(cfg.server.proxy['/api'].target).toBe('http://127.0.0.1:9911');
    expect(cfg.server.proxy['/ws'].target).toBe('http://127.0.0.1:9911');
  });

  it('HUB_BIND derives the proxy target when VITE_RUNTIME_TARGET is not set', async () => {
    process.env.HUB_BIND = '127.0.0.1:8788';
    const cfg = await loadConfig();
    expect(cfg.server.proxy['/api'].target).toBe('http://127.0.0.1:8788');
    expect(cfg.server.proxy['/ws'].target).toBe('http://127.0.0.1:8788');
  });

  it('a wildcard HUB_BIND host (0.0.0.0) maps to 127.0.0.1 for the proxy', async () => {
    process.env.HUB_BIND = '0.0.0.0:8788';
    const cfg = await loadConfig();
    expect(cfg.server.proxy['/api'].target).toBe('http://127.0.0.1:8788');
  });

  it('VITE_RUNTIME_TARGET wins over HUB_BIND', async () => {
    process.env.HUB_BIND = '127.0.0.1:8788';
    process.env.VITE_RUNTIME_TARGET = 'http://127.0.0.1:9911';
    const cfg = await loadConfig();
    expect(cfg.server.proxy['/api'].target).toBe('http://127.0.0.1:9911');
  });
});

// hub#798: the initial bundle carried ~1 MB of @ionic/core because Stencil's component modules
// have unannotated top-level calls (`proxyCustomElement(...)`), so Rollup treats every one of the
// 140+ components @ionic/vue re-exports as side-effectful and keeps them all — ion-datetime,
// ion-input-otp, ion-refresher… none of which the shell ever imports. Declaring @ionic/core's JS
// side-effect-free lets Rollup drop the unused ones. This is safe for custom-element registration:
// nothing registers at import time — @ionic/vue calls `defineCustomElement()` when a wrapper
// mounts or a controller is used, and `lib/ionic-wc.ts` registers OutfitKit's deps explicitly —
// so the set of REGISTERED elements is unchanged; only never-referenced dead bytes go away.
describe('vite.config tree-shakes @ionic/core (hub#798)', () => {
  it('marks @ionic/core JS modules as side-effect-free', async () => {
    const cfg = await loadConfig();
    const moduleSideEffects = cfg.build?.rollupOptions?.treeshake?.moduleSideEffects;
    expect(typeof moduleSideEffects).toBe('function');
    // pnpm-style resolved id of a core component nobody imports in the shell.
    const ionicCoreId =
      '/repo/node_modules/.pnpm/@ionic+core@8.8.9/node_modules/@ionic/core/components/ion-input-otp.js';
    expect(moduleSideEffects(ionicCoreId, false)).toBe(false);
  });

  it('splits stable vendors into their own cache groups (manualChunks)', async () => {
    const cfg = await loadConfig();
    const manualChunks = cfg.build?.rollupOptions?.output?.manualChunks;
    expect(typeof manualChunks).toBe('function');
    const pnpm = (pkg: string, rest: string) =>
      `/repo/node_modules/.pnpm/${pkg.replace('/', '+')}@1.0.0/node_modules/${pkg}/${rest}`;
    // Ionic is deliberately NOT grouped. Assigning a module through manualChunks makes it a chunk
    // entry whose exports are all preserved; for the @ionic/vue barrel (and @ionic/core through
    // it) that resurrects every tree-shaken component — measured +~300 kB of dead code (146 core
    // files back instead of 103). Ionic therefore stays in the entry chunk, tree-shaken.
    expect(manualChunks(pnpm('@ionic/core', 'components/ion-datetime.js'))).toBeUndefined();
    expect(manualChunks(pnpm('@ionic/vue', 'dist/index.js'))).toBeUndefined();
    expect(manualChunks(pnpm('@ionic/vue-router', 'dist/index.js'))).toBeUndefined();
    expect(manualChunks(pnpm('ionicons', 'components/icon.js'))).toBeUndefined();
    // Vue runtime + router + i18n.
    expect(manualChunks(pnpm('vue', 'dist/vue.runtime.esm-bundler.js'))).toBe('vendor-vue');
    expect(manualChunks(pnpm('@vue/runtime-core', 'dist/x.js'))).toBe('vendor-vue');
    expect(manualChunks(pnpm('vue-router', 'dist/x.js'))).toBe('vendor-vue');
    expect(manualChunks(pnpm('vue-i18n', 'dist/x.js'))).toBe('vendor-vue');
    expect(manualChunks(pnpm('@intlify/core-base', 'dist/x.js'))).toBe('vendor-vue');
    // OutfitKit + Lit (the ok-* registry main.ts loads at boot).
    expect(manualChunks(pnpm('@erplora/outfitkit', 'dist/ok-data-table.js'))).toBe('vendor-outfitkit');
    expect(manualChunks(pnpm('lit-html', 'lit-html.js'))).toBe('vendor-outfitkit');
    expect(manualChunks(pnpm('@lit/reactive-element', 'x.js'))).toBe('vendor-outfitkit');
    // App code and every other package keep Rollup's default assignment.
    expect(manualChunks('/repo/apps/web/src/main.ts')).toBeUndefined();
    expect(manualChunks(pnpm('mammoth', 'lib/index.js'))).toBeUndefined();
    expect(manualChunks(pnpm('swagger-ui-dist', 'swagger-ui-es-bundle.js'))).toBeUndefined();
    // vue-demi and friends must NOT be caught by a loose 'vue' match.
    expect(manualChunks(pnpm('vue-demi', 'lib/index.mjs'))).toBeUndefined();
  });

  it('leaves every other module side-effectful (default Rollup analysis)', async () => {
    const cfg = await loadConfig();
    const moduleSideEffects = cfg.build.rollupOptions.treeshake.moduleSideEffects;
    // Our own code, other packages, and any CSS keep the default (true = analyze/keep effects).
    expect(moduleSideEffects('/repo/apps/web/src/main.ts', false)).toBe(true);
    expect(
      moduleSideEffects('/repo/node_modules/@ionic/vue/dist/index.js', false),
    ).toBe(true);
    expect(
      moduleSideEffects('/repo/node_modules/@ionic/vue/css/core.css', false),
    ).toBe(true);
    // Defensive: if @ionic/core ever ships CSS through the graph, it must stay side-effectful.
    expect(
      moduleSideEffects('/repo/node_modules/@ionic/core/css/ionic.bundle.css', false),
    ).toBe(true);
  });
});

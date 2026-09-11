// hub#787: two dev benches could not coexist — the Vite port (5173 + strictPort) and the
// /api + /ws proxy target (:8787) were hardcoded, so a second bench (worktree) died on a busy
// port. These tests pin the contract: the port and the runtime target come from the environment
// (VITE_PORT, VITE_RUNTIME_TARGET, or derived from HUB_BIND), with today's values as defaults.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { availableParallelism } from 'node:os';
import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

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

// hub#1367: the gate's web stage was aborting pushes on the CLOCK rather than on the code. The
// `test` block declared `include` and `environment` and nothing else, so all 2178 unit tests ran
// on vitest's default `testTimeout: 5000` — a WALL-CLOCK budget. On a quiet machine the whole
// suite spends ~17 s of test time (mean ~8 ms per test) and nothing comes within an order of
// magnitude of 5 s; with the fleet loading the box (~19 worktrees on 15 cores) the very same
// tests get starved of CPU and vitest kills them. Measured on origin/develop@29e3a012: 0 failures
// at load ~10, 1 at load ~30, 40+ at load ~40 — the code identical in all three.
//
// A timeout is an anti-hang BACKSTOP, not an assertion: it must be loose enough that only a
// genuinely hung test trips it, and tight enough that a hung test still fails instead of wedging
// the gate forever. These assertions pin that property — deliberately as bounds and not as an
// equality, because the number is a budget to be tuned, while the guarantee is not.
describe('the unit suite survives a machine shared with the fleet (hub#1367)', () => {
  it('gives a test far more headroom than the 5 s default before calling it hung', async () => {
    const cfg = await loadConfig();
    // 5000 (the default) is what made a config-import test time out under load.
    expect(cfg.test.testTimeout).toBeGreaterThanOrEqual(20_000);
    // …but a hung test must still FAIL, and reasonably soon: the gate blocks the whole fleet.
    expect(cfg.test.testTimeout).toBeLessThanOrEqual(120_000);
  });

  it('gives hooks the same headroom: a starved beforeEach is not a broken beforeEach', async () => {
    const cfg = await loadConfig();
    expect(cfg.test.hookTimeout).toBeGreaterThanOrEqual(20_000);
    expect(cfg.test.hookTimeout).toBeLessThanOrEqual(120_000);
  });

  it('never retries: a red test stays red (cero regresiones)', async () => {
    const cfg = await loadConfig();
    // `retry` would turn this same starvation green — and with it every real flake the suite
    // exists to catch. The fix is to stop measuring the machine, not to re-roll the dice.
    expect(cfg.test.retry ?? 0).toBe(0);
  });
});

// hub#1364: the `test` block never bounded the pool, so vitest fell back to its own default —
// `Math.max(availableParallelism() - 1, 1)` (vitest 4.1.10, `resolveMaxWorkers`). That number is
// the WHOLE machine, and this suite no longer runs alone on one: since hub#1466 it runs as the
// `pnpm verify` job of `test-web.yml`, on `ci-runner-1` (a cx53: 16 vCPU / 32 GB) which serves SIX
// runner slots. Every other pool there is already capped — `CARGO_BUILD_JOBS=8` per slot, exactly
// so that six cargos are not 96 rustc — and vitest was the last one that was not: six web jobs
// would ask for 15 forks each, 90 processes on 16 vCPU. A pool that sizes itself off the machine
// is not sizing itself off what it is allowed to take.
//
// The contract is a CEILING, not a target: the value may only ever LOWER vitest's own default,
// never raise it, so the same config is also safe on the 2-core GitHub-hosted fallback
// (`vars.CI_RUNNER_LABEL` unset) where the default is already 1. `VITEST_MAX_WORKERS` still wins
// over anything declared here (vitest applies it last), which is the escape hatch for a one-off.
describe('the vitest pool is bounded, not sized off the machine (hub#1364)', () => {
  const vitestDefaultWorkers = Math.max(availableParallelism() - 1, 1);

  it('caps the pool instead of leaving vitest to take the whole box', async () => {
    const cfg = await loadConfig();
    expect(typeof cfg.test.maxWorkers).toBe('number');
    expect(cfg.test.maxWorkers).toBeGreaterThanOrEqual(1);
    // Six slots on 16 vCPU: the cap is what makes concurrent web jobs share the runner instead of
    // each claiming it whole. A number, not a percentage — a percentage is still the machine.
    expect(cfg.test.maxWorkers).toBeLessThanOrEqual(4);
  });

  it('is a ceiling: it never asks for more workers than vitest itself would', async () => {
    const cfg = await loadConfig();
    // On a small runner (2 vCPU → default 1) this must not RAISE the pool. Bounding the fleet's
    // shared runner is not worth oversubscribing every other machine that runs this suite.
    expect(cfg.test.maxWorkers).toBeLessThanOrEqual(vitestDefaultWorkers);
  });

  it('follows the machine DOWN: on a 2-core box the cap resolves to 1, not 4', async () => {
    // The two assertions above only bite on a ≤4-core machine, and none of the machines that run
    // this suite today has that few (dev Mac and ci-runner-1 are both 16). Simulate the 2-vCPU
    // GitHub-hosted fallback so a hardcoded `maxWorkers: 4` — which drops the ceiling and
    // oversubscribes the box vitest itself would size at 1 — goes red on EVERY machine.
    vi.resetModules();
    vi.doMock('node:os', async (importOriginal) => {
      const actual = await importOriginal<typeof import('node:os')>();
      const availableParallelism = () => 2;
      return { ...actual, availableParallelism, default: { ...actual, availableParallelism } };
    });
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const cfg = (await import('./vite.config.ts')).default as any;
      expect(cfg.test.maxWorkers).toBe(1);
    } finally {
      vi.doUnmock('node:os');
      vi.resetModules();
    }
  });
});

// Regression test for ERPlora/hub#1752 — a test file nobody runs is a green that means nothing.
//
// `test.include` in `vite.config.ts` is an ALLOWLIST, not a glob over the tree, and the four
// bench files under `tests/` were listed one by one. Adding a fifth and forgetting the line does
// not fail: vitest reports "No test files found" for that path and the suite stays green without
// it — which is the same shape of hole this batch is closing in the visual bench.
describe('vitest include covers tests/ (hub#1752)', () => {
  it('REGRESIÓN: ningún `tests/*.test.ts` del árbol se queda sin correr', async () => {
    const cfg = await loadConfig();
    const testsDir = fileURLToPath(new URL('./tests', import.meta.url));
    const onDisk = readdirSync(testsDir).filter((f) => f.endsWith('.test.ts'));
    // If this ever reads zero, the loop below would prove nothing at all.
    expect(onDisk.length).toBeGreaterThanOrEqual(4);

    const patterns: string[] = cfg.test.include;
    for (const file of onDisk) {
      const covered = patterns.some(
        (p) => p === `tests/${file}` || p === 'tests/*.test.ts' || p === 'tests/**/*.test.ts',
      );
      expect(
        covered,
        `tests/${file} no lo cubre ningún patrón de test.include → vitest NO lo corre, ` +
          'y su rojo no lo vería nadie (hub#1752)',
      ).toBe(true);
    }
  });
});

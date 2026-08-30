// Regression test for ERPlora/hub#1250 — pins `updateSnapshots` in `playwright.config.ts` to the
// decision made by `src/lib/visual-baseline-gate.ts`.
//
// Why this needs its own assertion and not just the pure-function tests: Playwright's OWN
// default for `updateSnapshots` is `'missing'`, which quietly CREATES a missing baseline PNG and
// marks the test green — in any environment, CI included. `resolveUpdateSnapshotsMode` alone
// proves the decision function is correct; this test proves the config file actually WIRES that
// decision into Playwright instead of leaving the library default in charge, which is exactly the
// kind of wiring gap hub#1240's contract test (`test-web-workflow.test.sh`) exists to catch for
// the workflow side.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const ENV_KEYS = ['CI', 'HUB_UPDATE_BASELINES'] as const;
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

// The config reads the env at module evaluation → re-import fresh each time (same pattern as
// `vite.config.test.ts`). Importing it does not start any server: `webServer` is plain data.
async function loadConfig() {
  vi.resetModules();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (await import('./playwright.config.ts')).default as any;
}

describe('playwright.config updateSnapshots (hub#1250)', () => {
  it('REGRESSION: a normal CI run must fail on a missing baseline, never recreate it', async () => {
    process.env.CI = '1';
    const cfg = await loadConfig();
    expect(cfg.updateSnapshots).toBe('none');
  });

  it('the dedicated baseline-update run (visual-baselines.yml) regenerates every screenshot', async () => {
    process.env.CI = '1';
    process.env.HUB_UPDATE_BASELINES = '1';
    const cfg = await loadConfig();
    expect(cfg.updateSnapshots).toBe('all');
  });

  it('outside CI, a missing baseline is created without failing (authoring a new spec)', async () => {
    const cfg = await loadConfig();
    expect(cfg.updateSnapshots).toBe('missing');
  });
});

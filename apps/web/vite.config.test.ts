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

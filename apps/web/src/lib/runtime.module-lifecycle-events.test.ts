// Regression test for ERPlora/hub#1336.
//
// hub#1211 gave the SDK's `queryOptional` short-circuit a cache of ACTIVE module ids
// (`refreshActiveModuleIds`), refreshed at client construction, on every login and — for OTHER
// tabs/devices — on the `module.installed` WS event. hub#1317 (PR #1335) then made
// activate/deactivate/uninstall broadcast `module.activated` / `module.deactivated` /
// `module.uninstalled` with the same envelope and the same scope, and the shell wired the nav
// (`App.vue`) and «Mis apps» (`AppsPage.vue`) to them — but NOT this cache.
//
// Without this fix, activating `modifiers` from the back office leaves the till open on the counter
// short-circuiting optional queries against yesterday's set until someone reloads it: the symmetric
// half of the hole hub#1211 closed for install.
//
// The subscriptions are exercised through the client the shell actually builds (`getClient()`), not
// by grepping the source: a listener registered for the wrong event name, or one that no longer
// re-asks the runtime, reads identically in the text and is exactly what this must catch.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { subscriptions, RecordingTransport } = vi.hoisted(() => {
  /** Handlers the shell subscribed on the client, by event name. */
  const subscriptions = new Map<string, Set<(payload: unknown) => void>>();

  /**
   * Stand-in for `HttpWsTransport`: the real one opens the `/ws` socket on the first subscription,
   * which a unit test has no business doing. Everything else in the client stays real.
   */
  class RecordingTransport {
    subscribe(event: string, cb: (payload: unknown) => void): () => void {
      let set = subscriptions.get(event);
      if (!set) {
        set = new Set();
        subscriptions.set(event, set);
      }
      set.add(cb);
      return () => set?.delete(cb);
    }
  }

  return { subscriptions, RecordingTransport };
});

vi.mock('@erplora/module-sdk', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@erplora/module-sdk')>();
  return { ...actual, HttpWsTransport: RecordingTransport };
});

const HUB_SESSION_KEY = 'erplora.hub_session';

/** What `GET /api/modules` answers next — swapped mid-test to play the OTHER tab's change. */
let installed: { id: string; name: string; status: string; version: string }[] = [];

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, String(value));
    },
  } as Storage;
}

/** One macrotask: lets a fire-and-forget refresh (`void refreshActiveModuleIds()`) advance. */
const tick = () => new Promise((r) => setTimeout(r, 0));

/**
 * Waits for a refresh to LAND, instead of assuming one tick is enough.
 *
 * The fleet shares this machine, so a fixed `setTimeout(0)` is the difference between a test that
 * measures the wiring and one that measures the load average. Bounded on purpose: it fails saying
 * what it waited for rather than hanging until the runner's own timeout.
 */
async function until(what: string, ready: () => boolean): Promise<void> {
  for (let i = 0; i < 500; i += 1) {
    if (ready()) return;
    await tick();
  }
  throw new Error(`timed out waiting for ${what}`);
}

const idsOf = (set: ReadonlySet<string> | undefined) => [...(set ?? [])].sort().join(',');

/** Builds the shell's client on a hub with a live session and waits for the initial seed to land. */
async function bootShell(): Promise<typeof import('./runtime')> {
  vi.resetModules();
  subscriptions.clear();
  const runtime = await import('./runtime');
  runtime.getClient();
  await until('the initial seed', () => idsOf(runtime.activeModuleIds()) === 'sales');
  return runtime;
}

/** Delivers a runtime WS frame to whoever the shell subscribed for it. */
function broadcast(event: string): void {
  expect([...subscriptions.keys()], `the shell must subscribe to '${event}'`).toContain(event);
  for (const handler of subscriptions.get(event) ?? []) handler({ type: event, module_id: 'modifiers' });
}

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  localStorage.setItem(HUB_SESSION_KEY, 'sess-open-till');
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve(
            String(url).includes('/api/modules') ? { ok: true, data: installed } : { ok: true, data: {} },
          ),
      }),
    ),
  );
  installed = [
    { id: 'sales', name: 'Sales', status: 'active', version: '1.0.0' },
    { id: 'modifiers', name: 'Modifiers', status: 'inactive', version: '1.0.0' },
  ];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// Each case pays for the module graph's transform (Ionic, vue-i18n) on a machine the whole fleet
// shares: a generous budget, so a slow import can never read as a broken subscription.
const BOOT_TIMEOUT_MS = 60_000;

describe('the active-module cache follows the module lifecycle of ANOTHER tab (hub#1336)', () => {
  it.each([
    ['module.activated'],
    ['module.deactivated'],
    ['module.uninstalled'],
    // hub#1211's own wiring, kept in the same battery: it must not regress while the three are added.
    ['module.installed'],
  ] as const)(
    '%s re-asks the runtime which modules are active',
    async (event) => {
      const runtime = await bootShell();

      // The back office activated `modifiers`; this tab only hears about it through the WS event.
      installed = installed.map((m) => (m.id === 'modifiers' ? { ...m, status: 'active' } : m));
      broadcast(event);

      await until(`the refresh triggered by '${event}'`, () => idsOf(runtime.activeModuleIds()) === 'modifiers,sales');
    },
    BOOT_TIMEOUT_MS,
  );

  it(
    'a lifecycle event whose refresh FAILS keeps the previous answer, never an empty set',
    async () => {
      // Best-effort by contract (`refreshActiveModuleIds`): publishing an empty set on a transient
      // error would make every optional query look absent — the opposite of what hub#1211 bought.
      const runtime = await bootShell();

      vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'));
      broadcast('module.deactivated');
      await tick();
      await tick();

      expect(runtime.activeModuleIds()).toEqual(new Set(['sales']));
    },
    BOOT_TIMEOUT_MS,
  );
});

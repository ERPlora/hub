/**
 * Recovery for a screen whose code never arrives (hub#1518).
 *
 * Every view in the shell is loaded on demand (`() => import('../views/X.vue')`), so opening a
 * screen is a network fetch. When that fetch dies — the till hops from wifi to 4G, the chunk went
 * stale after a deploy, or, in CI, the runner's network blinks (`net::ERR_NETWORK_CHANGED` while
 * six jobs create and tear down Docker bridges) — the router throws
 * `TypeError: Failed to fetch dynamically imported module: …`.
 *
 * On the FIRST navigation that is fatal and silent: `main.ts` mounts inside
 * `router.isReady().then(...)`, so the rejection leaves the app unmounted — a white page, no
 * message, no way out but reloading by hand. That is what CI kept catching as a "flaky e2e".
 *
 * **Retrying the same `import()` in place does not work.** Per the HTML module map, a module URL
 * that failed to fetch is remembered as failed: the second call rejects without touching the
 * network. Only a fresh document clears it — hence a reload, and only one, guarded by a mark in
 * `sessionStorage` so a permanently broken build can never turn the till into a boot loop.
 *
 * The ladder:
 *   1. first navigation, not tried yet → reload the target path once;
 *   2. it failed again after that reload (or the mark cannot be stored) → the caller paints a
 *      visible message; never a blank page;
 *   3. navigating inside an app that is already open → the router simply aborts, so the person
 *      keeps the screen (and the half-typed order) they were on; the caller says it out loud.
 */

/** The slice of `Storage` this module needs. */
export interface RecoveryStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** Where the "I already reloaded for this screen" mark lives. Per tab, on purpose. */
export const VIEW_LOAD_RECOVERY_KEY = 'erplora.viewLoadRecovery';

// How each engine words "the file behind this screen never arrived". Chromium and Firefox differ,
// and Vite's own preload helper adds a fourth wording of its own for the stylesheet half.
const VIEW_LOAD_ERROR_PATTERNS = [
  'failed to fetch dynamically imported module',
  'error loading dynamically imported module',
  'importing a module script failed',
  'unable to preload css',
];

/**
 * True when `error` is the browser failing to FETCH a view, as opposed to the view's own code
 * throwing. The distinction is the whole safety of this module: reloading on a genuine bug would
 * hide it behind a loop, so anything we do not recognise is left for the caller to report.
 */
export function isViewLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return VIEW_LOAD_ERROR_PATTERNS.some((pattern) => message.includes(pattern));
}

export type ViewLoadOutcome =
  /** Reloading the target path now; a fresh document gets a clean module map. */
  | 'reload'
  /** Already reloaded once (or cannot remember): show the failure instead of a blank page. */
  | 'exhausted'
  /** The app is up and stays where it is; tell the person the screen would not open. */
  | 'notify'
  /** Not a fetch failure — the caller reports it as the bug it is. */
  | 'ignored';

function readMark(storage: RecoveryStorage): string | null {
  try {
    return storage.getItem(VIEW_LOAD_RECOVERY_KEY);
  } catch {
    // Storage blocked (locked-down browser, third-party context): treated as "no mark", and the
    // write below will fail too, which is what stops the reload.
    return null;
  }
}

/** Writes the mark and confirms it stuck: without persistence a reload would loop forever. */
function markPersisted(storage: RecoveryStorage, path: string): boolean {
  try {
    storage.setItem(VIEW_LOAD_RECOVERY_KEY, path);
    return storage.getItem(VIEW_LOAD_RECOVERY_KEY) === path;
  } catch {
    return false;
  }
}

/** Forgets the mark once a navigation lands, so a later hiccup can recover too. Never throws. */
export function clearViewLoadRecovery(storage: RecoveryStorage): void {
  try {
    storage.removeItem(VIEW_LOAD_RECOVERY_KEY);
  } catch {
    /* nothing to forget if there was nowhere to remember */
  }
}

/**
 * Decides what to do with a navigation error and, for the reload rung, does it.
 *
 * `isInitial` means "the document has not shown a route yet" — the only case where an aborted
 * navigation leaves a blank page.
 */
export function recoverFromViewLoadError(
  error: unknown,
  nav: { toPath: string; isInitial: boolean },
  io: { storage: RecoveryStorage; reload: (path: string) => void },
): ViewLoadOutcome {
  if (!isViewLoadError(error)) return 'ignored';
  if (!nav.isInitial) return 'notify';
  if (readMark(io.storage) === nav.toPath) return 'exhausted';
  if (!markPersisted(io.storage, nav.toPath)) return 'exhausted';
  io.reload(nav.toPath);
  return 'reload';
}

/** `sessionStorage`, or a storage that remembers nothing if the browser denies access. */
export function browserRecoveryStorage(): RecoveryStorage {
  try {
    // Reading the property itself throws when storage is disabled, so it lives inside the try.
    const storage = window.sessionStorage;
    if (storage) return storage;
  } catch {
    /* fall through to the no-op below: no memory means no reload, by design */
  }
  return {
    getItem: () => null,
    setItem: () => {
      throw new Error('storage unavailable');
    },
    removeItem: () => {},
  };
}

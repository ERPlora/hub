/**
 * «Nothing reached the hub» told apart from «the hub answered something bad» (hub#1743).
 *
 * Every screen of the shell talks to the runtime over `fetch`, so every screen can fail for those
 * two reasons — and once the rejection lands in a `catch` they look identical. Painting the wrong
 * one is what hub#1743 reported: with the wifi down, the module screen told the owner to «check
 * that the module is still installed and active», so the person went looking for an app that
 * nobody had touched while the router was the thing that was dead.
 *
 * The fact that separates them is already in the failure. A `fetch` that never reached anybody
 * rejects with a `TypeError` — each engine words it differently, which is why the list below is
 * the contract — whereas a hub that answered 500 gives us a status line we made up ourselves
 * (`navigation → 500`). The browser also keeps a flag, and BOTH are read: the flag is not enough
 * (it is `true` on a laptop attached to a router with no uplink, the commonest way a shop loses
 * the internet) and the wording is not enough either (the app may have started with no network at
 * all). Either one is enough to say the connection is the thing to talk about.
 *
 * The shape follows `isViewLoadError` in `router/view-load-recovery.ts` — same problem, one floor
 * up — and the reason this is a lib and not a helper inside `ModuleView` is that the rule belongs
 * to the whole shell: the strip in `AppPage` and the module screen ask the same question.
 */
import { computed, ref } from 'vue';

/**
 * How each engine words «this request reached nobody». There is no code to branch on, so the
 * wording is all there is; anything not on this list is treated as a real answer on purpose,
 * because guessing wrong in that direction hides a genuine fault behind «check your wifi».
 */
const NETWORK_FAILURE_PATTERNS = [
  'failed to fetch', // Chromium
  'networkerror when attempting to fetch resource', // Firefox
  'load failed', // Safari
  'network connection was lost', // Safari / iOS
  'network request failed',
];

/**
 * …and how each engine words «that SCRIPT did not load», which is a different claim and must not be
 * mistaken for the one above.
 *
 * A dynamic `import()` throws these both when nothing answered AND when the server answered 404 or
 * 500 — the wording is identical, and Chromium's even contains «failed to fetch» word for word. In
 * this shell the 404 half is not an edge case, it is THE case hub#1743 is about: a module that is
 * no longer installed (or a bundle url left over from the version before an update, hub#935) makes
 * `/modules/<id>/dist/<id>.esm.js` answer 404 with the network in perfect health. Reading that as
 * an outage would print «no internet connection» over exactly the fault whose own sentence —
 * «check that the module is still installed and active» — this file exists to protect.
 *
 * So on their own they claim nothing. `navigator.onLine` still decides above them: with the flag
 * down, a failed import IS the outage and gets told as one.
 */
const SCRIPT_LOAD_FAILURE_PATTERNS = [
  'failed to fetch dynamically imported module', // Chromium
  'error loading dynamically imported module', // Firefox
  'importing a module script failed', // Safari
  'unable to preload css', // Vite's own preload helper, for the stylesheet half
];

/**
 * True when `error` is the browser failing to REACH the other end, as opposed to the other end
 * answering something we did not like.
 */
export function isNetworkFailure(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  // Checked first and on purpose: «Failed to fetch dynamically imported module» contains «failed to
  // fetch», so without this the ambiguous wording would be swallowed by the unambiguous list.
  if (SCRIPT_LOAD_FAILURE_PATTERNS.some((pattern) => message.includes(pattern))) return false;
  return NETWORK_FAILURE_PATTERNS.some((pattern) => message.includes(pattern));
}

/** `navigator.onLine`, defensively: outside a browser (SSR, a bare test) there is nothing to ask. */
function navigatorIsOnline(): boolean {
  return typeof navigator === 'undefined' || navigator.onLine !== false;
}

const online = ref(navigatorIsOnline());

// One pair of listeners for the life of the document: the flag is the browser's, so there is
// exactly one of it and nothing to tear down. Reading it once at boot would be the bug — a till
// that lost the network after opening would never notice, which is the whole point of a strip that
// stays up «while» there is no connection.
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    online.value = true;
  });
  window.addEventListener('offline', () => {
    online.value = false;
  });
}

// hub#2085 — the second fact, and the one the flag cannot give: whether the HUB answers. The flag is
// `true` on a till plugged into a router with no uplink, which is the commonest way a shop loses
// the internet, so a band that only read the flag stayed down through exactly the outage it was
// built for. The shell now asks the hub itself, lightly, and this is the verdict.
const hubReachable = ref(true);

/** Whether the shell can currently reach the hub: the browser has a network AND the hub answers. */
export const isOnline = computed<boolean>(() => online.value && hubReachable.value);

/** The same fact the other way round, for the templates that read better that way. */
export const isOffline = computed<boolean>(() => !isOnline.value);

/**
 * Why the shell is offline, for the band that has to say it without lying.
 *
 * `'network'` wins over `'hub'` on purpose: when the browser itself reports no network, the wifi is
 * the sentence the person can act on, whatever the hub did or did not answer. `'hub'` is the other
 * case — the device believes it is online and ERPlora is not answering — where the fault may be the
 * shop's uplink or ours, and the wording has to leave room for both.
 */
export type OfflineCause = 'network' | 'hub';
export const offlineCause = computed<OfflineCause | null>(() => {
  if (!online.value) return 'network';
  if (!hubReachable.value) return 'hub';
  return null;
});

/** How often the hub is asked while everything is fine. One light request; a till is not a load. */
export const HUB_PROBE_INTERVAL_MS = 30_000;
/** How often it is asked once an answer was missed, so the band rises — and falls — without a wait. */
export const HUB_PROBE_RETRY_MS = 5_000;
/**
 * How long a probe waits before «nothing came back» is the verdict. With a router that has no
 * uplink the request goes nowhere and the browser's own timeout is over a minute; a band that takes
 * a minute to rise is a band that rises after the cashier gave up.
 */
export const HUB_PROBE_TIMEOUT_MS = 10_000;
/** Misses in a row before the hub is called unreachable: one can be a restart, and must not flash. */
const MISSES_BEFORE_OUTAGE = 2;

export interface HubProbeOptions {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

/**
 * The question asked of the hub: «are you there?». Resolves when ANYTHING came back — a 500 is an
 * answer, and reachability is a fact about the network, not about the hub's health, which the
 * screen that got the 500 already tells in its own words. Rejects only when nothing came back: the
 * network failure every engine spells differently, or a request that never finished.
 */
export function makeHubProbe(baseUrl: string, options: HubProbeOptions = {}): () => Promise<void> {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const timeoutMs = options.timeoutMs ?? HUB_PROBE_TIMEOUT_MS;
  const url = `${baseUrl.replace(/\/$/, '')}/healthz`;
  return async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      // `no-store`: a cached «ok» from before the router died is exactly the lie being fought here.
      await fetchImpl(url, { method: 'GET', cache: 'no-store', signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  };
}

export interface HubWatchOptions {
  /** See {@link makeHubProbe}. Injected so the watch itself never touches `fetch`. */
  probe: () => Promise<void>;
  intervalMs?: number;
  retryMs?: number;
}

interface HubWatch {
  askNow(): void;
  stop(): void;
}

let activeWatch: HubWatch | null = null;

/**
 * Starts asking the hub whether it is there, and keeps `isOnline` honest with the answers.
 *
 * Rules, each of them a rule and not a preference:
 * - **Two misses in a row, not one.** A single miss can be the hub restarting for a deploy, and a
 *   band that flashes on every deploy is a band nobody reads.
 * - **One answer clears it.** The outage is over the moment anything comes back.
 * - **A hidden tab is left alone.** Nobody is reading it, so there is nobody to warn; the moment it
 *   is looked at again it is asked at once, because «does it still work?» is the first question.
 * - **A screen that just failed to reach the hub makes it ask at once** ({@link reportNetworkFailure}):
 *   waiting up to 30 s to confirm what a failure just proved would leave the band behind the screen.
 * - **The browser's own `online` event asks at once too**: the flag came back, but the flag is not
 *   a promise, and the band must not fall on a promise.
 *
 * Returns the function that stops it. Starting a second watch stops the first: there is one hub
 * and one verdict.
 */
export function startHubWatch(options: HubWatchOptions): () => void {
  activeWatch?.stop();

  const intervalMs = options.intervalMs ?? HUB_PROBE_INTERVAL_MS;
  const retryMs = options.retryMs ?? HUB_PROBE_RETRY_MS;
  let misses = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight = false;
  let stopped = false;

  const visible = (): boolean =>
    typeof document === 'undefined' || document.visibilityState !== 'hidden';

  const schedule = (ms: number): void => {
    if (stopped) return;
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => void ask(), ms);
  };

  const ask = async (): Promise<void> => {
    if (stopped || inFlight) return;
    if (!visible()) return; // asked again on `visibilitychange`
    inFlight = true;
    try {
      await options.probe();
      misses = 0;
      hubReachable.value = true;
      schedule(intervalMs);
    } catch {
      misses += 1;
      if (misses >= MISSES_BEFORE_OUTAGE) hubReachable.value = false;
      schedule(retryMs);
    } finally {
      inFlight = false;
    }
  };

  const onVisibility = (): void => {
    if (visible()) void ask();
  };
  const onOnline = (): void => void ask();

  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisibility);
  if (typeof window !== 'undefined') window.addEventListener('online', onOnline);

  const watch: HubWatch = {
    askNow: () => void ask(),
    stop: () => {
      stopped = true;
      if (timer !== undefined) clearTimeout(timer);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibility);
      }
      if (typeof window !== 'undefined') window.removeEventListener('online', onOnline);
      if (activeWatch === watch) activeWatch = null;
      // No watch, no verdict: a stopped watch must not leave the band up for ever.
      hubReachable.value = true;
    },
  };
  activeWatch = watch;
  void ask();
  return watch.stop;
}

/**
 * Told by a screen whose request reached nobody (hub#1743 already knows which those are), so the
 * hub is asked at once instead of at the next tick of the clock. A no-op with no watch running.
 */
export function reportNetworkFailure(): void {
  activeWatch?.askNow();
}

/**
 * Whether a failure should be told as «there is no connection» rather than as a fault of whatever
 * was being loaded.
 *
 * Two ways in, and both are needed: the browser says there is no network, or the failure itself
 * says the request reached nobody. What it deliberately does NOT do is claim the network whenever
 * anything fails — an error that came back from a hub that is plainly reachable keeps its own
 * sentence, because «check your connection» over a real fault is the same lie in reverse.
 */
export function isOfflineError(error: unknown): boolean {
  return !online.value || isNetworkFailure(error);
}

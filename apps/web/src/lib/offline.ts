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
import { computed, readonly, ref, type Ref } from 'vue';

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

/** Whether the browser currently believes it has a network. Reactive. */
export const isOnline: Readonly<Ref<boolean>> = readonly(online);

/** The same fact the other way round, for the templates that read better that way. */
export const isOffline = computed<boolean>(() => !online.value);

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

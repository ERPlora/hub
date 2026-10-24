// Runs before every test file of the hub (`test.setupFiles` in vite.config.ts, as packages/ui's; proven by
// vitest.setup.test.ts): no real timer outlives a test (hub#197, hub#199). Vitest tears the page's window down at the
// end of a file, and a timer still armed then fires into a missing window — an «Unhandled error» and exit 1 with
// every test green.
// Each test's end leaves the page as a person does: it unmounts what @vue/test-utils mounted and the test did not
// (AppPage clears its tabbar's 450 ms scroll hint then, which emptying the document alone does not), empties the
// document, lets what that sets off run, and fails if a real timeout or interval the test armed is still pending,
// naming where it was armed. It watches the real timers, not Vitest's fake clock: a file with fake timers of its
// own works as before, and a timer put on a fake clock dies with that clock — it cannot outlive the page.
// A page mounted alone paints the icons the running app paints (`createShell` registers them when the app starts), and
// Ionic's elements attach as in a browser (`fillHappyDomGaps`, as packages/ui's own setup does).
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { fillHappyDomGaps } from '@erplora/ui/testing';
import { enableAutoUnmount } from '@vue/test-utils';
import { afterEach, beforeEach } from 'vitest';
import { render, toRaw } from 'vue';

// The hub does not depend on ionicons itself: its registry is global (`window.Ionicons`), so the copy @erplora/ui
// installs registers the shell's icons, as apps/inventory's and apps/customer's harnesses did; the shell's registry
// itself, as its barrel would boot the whole shell.
import { addIcons } from './packages/ui/node_modules/ionicons';
import { ION_ICONS } from './packages/ui/src/shell/icons';

type Timer = ReturnType<typeof setTimeout>;
type Handler = (...args: unknown[]) => void;

const HUB_DIR = `${dirname(fileURLToPath(import.meta.url))}/`;

const real = { setTimeout, clearTimeout, setInterval, clearInterval };

/** The real timers armed since the running test began that have neither run nor been cleared, and where each was
 *  armed. */
const armed = new Map<Timer, string>();

/** «setTimeout 450 ms at <caller>», plus the first frame of the hub's own code when the caller is a library's. */
function armedAt(kind: string, delay: unknown): string {
  // 0: «Error», 1: this function, 2: the wrapper below; then whoever armed the timer.
  const frames = (new Error().stack ?? '').split('\n').slice(3).map((line) => line.trim().replace(/^at /, '').replace(HUB_DIR, ''));
  const own = frames.find((frame) => !frame.includes('/node_modules/'));
  const where = own && own !== frames[0] ? `${frames[0]} … ${own}` : frames[0];
  return `${kind} ${Number(delay ?? 0)} ms at ${where}`;
}

globalThis.setTimeout = ((handler: Handler, delay?: number, ...args: unknown[]) => {
  // Not a function: Node's own error, as without this setup.
  if (typeof handler !== 'function') return real.setTimeout(handler, delay, ...args);
  const id = real.setTimeout(() => {
    armed.delete(id);
    handler(...args);
  }, delay);
  armed.set(id, armedAt('setTimeout', delay));
  return id;
}) as typeof setTimeout;

globalThis.setInterval = ((handler: Handler, delay?: number, ...args: unknown[]) => {
  const id = real.setInterval(handler, delay, ...args);
  armed.set(id, armedAt('setInterval', delay));
  return id;
}) as typeof setInterval;

// Node clears either kind with either function. A timer kept in reactive state comes back as Vue's proxy of Node's
// timer object, which Node clears all the same: the raw object is the one watched.
globalThis.clearTimeout = ((id?: Timer) => {
  if (id != null) armed.delete(toRaw(id));
  real.clearTimeout(id);
}) as typeof clearTimeout;

globalThis.clearInterval = ((id?: Timer) => {
  if (id != null) armed.delete(toRaw(id));
  real.clearInterval(id);
}) as typeof clearInterval;

/** Unmounts what @vue/test-utils mounted since the last call and is still mounted. */
let unmountMounted = (): void => {};
enableAutoUnmount((unmount) => {
  unmountMounted = unmount;
});

// Vue arms a one-off 3 s timer (its devtools hook) the first time it renders in a browser: armed here, before any
// test watches, it is no test's.
if (typeof document !== 'undefined') render(null, document.createElement('div'));

// Without them each `ion-icon` warns with its whole element and tries the network, and each Ionic element logs a
// TypeError: megabytes of output per file, which the run's main process must take in while the files ask it for their
// modules (a cold import then outlasts a test). Both are no-ops without a DOM.
if (typeof window !== 'undefined') addIcons(ION_ICONS);
fillHappyDomGaps();

beforeEach(() => {
  // What the file armed before its tests (this setup, its imports, a `beforeAll`) is not the test's.
  armed.clear();
});

afterEach(async () => {
  try {
    // What the test itself armed is counted before any tick can run it: on a loaded machine a short timer ran while
    // the setup let the page's teardown run, slipped through and fired into the next test (a 0 ms one always did).
    const armedByTest = new Set(armed.keys());
    unmountMounted();
    if (typeof document !== 'undefined') document.body.innerHTML = '';
    const left = [...armed].filter(([id]) => armedByTest.has(id));
    for (const [id] of left) {
      real.clearTimeout(id);
      armed.delete(id);
    }
    // What leaving the page sets off arms its timers in the next ticks: let them run before counting those.
    for (let i = 0; i < 3; i++) await new Promise((resolve) => real.setTimeout(resolve, 0));
    const outlived = [...left.map(([, where]) => where), ...armed.values()];
    if (outlived.length) {
      throw new Error(`real timers still armed when the test ends (each would fire into the torn-down page):\n${outlived.join('\n')}`);
    }
  } finally {
    // A failed test's leftovers must not fire into the next one.
    for (const id of armed.keys()) real.clearTimeout(id);
    armed.clear();
  }
});

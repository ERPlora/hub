// The SaaS's demo door as demo.spec.ts reads it (hub#1048): where «Try the demo» lands when the SaaS opens no demo,
// and what the run says then. A refused try comes back to the door itself as `/demo/?state=<outcome>` (public/demo.py
// of the SaaS, drawn with `data-testid="demo-state-<outcome>"`); the spec only waited for the demo's host, and a door
// that said «throttled» failed the run as a demo too slow to be ready. Since hub#1061 the spec has no clock of its own
// for the demo, and the door's own 30 s (`not_ready`, PUBLIC-F29 of the SaaS) is waited past with its «Try again».

import type { DemoRow } from './demo-born';

/** What the README's recipes start the SaaS of a stack with. Every pass of demo.spec.ts starts two demos from
 *  127.0.0.1, and the SaaS's own limit, 3 new demos an hour per address (its `DEMO_SPAWN_RATELIMIT`, counted in the
 *  memory of its runserver), refused the second pass of the hour. The production limit does not change. */
export const E2E_DEMO_SPAWN_RATELIMIT = '100/h';

/** The outcome the door answered «Try the demo» with: `throttled` for `<door>?state=throttled`; `null` anywhere else,
 *  the demo's host or the door without one, where a demo being prepared is waited for. */
export function doorOutcome(url: string, door: string): string | null {
  const at = new URL(url);
  const expected = new URL(door);
  if (at.origin !== expected.origin || at.pathname !== expected.pathname) return null;
  return at.searchParams.get('state') || null;
}

/** Why «Try the demo» opened no demo, for the failure of the run: the door's outcome and, when it is the limit of new
 *  demos per address, how the SaaS of the stack is started so that it does not refuse the next pass. */
export function noDemoBecause(outcome: string): string {
  const said = `The SaaS's demo door answered «Try the demo» with state=${outcome} instead of opening a demo`;
  if (outcome !== 'throttled') return `${said} (its data-testid="demo-state-${outcome}").`;
  return (
    `${said}: this address started more new demos this hour than its DEMO_SPAWN_RATELIMIT lets (3/h unless its ` +
    `runserver sets it, and each pass of demo.spec.ts starts two). Start the SaaS of the stack with ` +
    `DEMO_SPAWN_RATELIMIT=${E2E_DEMO_SPAWN_RATELIMIT}, as the recipe of tests/e2e/README.md does, or restart its ` +
    `runserver to clear the count.`
  );
}

/** The door's outcome for a demo it gave up waiting for after its own 30 s (its page asks every second,
 *  `frontend/demo-wait.ts` of the SaaS), or one the Hub could not prepare yet and retries on its own: its «Try again»
 *  (`data-testid="demo-retry"`) waits for the same demo (PUBLIC-F29, step 3). */
export const NOT_READY = 'not_ready';

/** Why «Try the demo» opened no demo when the door answered `outcome`, to fail the run at once; `null` for a demo the Hub
 *  is still preparing (`demo`, the newest of the registry) once the door's 30 s ran out: the run waits for it again with
 *  «Try again», with no clock of its own (a demo that never opens is cut by the test's timeout). */
export function whyNoDemo(outcome: string, demo: DemoRow | null): string | null {
  if (outcome !== NOT_READY) return noDemoBecause(outcome);
  const said = `The SaaS's demo door answered with state=${NOT_READY}`;
  if (demo === null) return `${said}, and there is no demo in the registry of this run for it to wait for.`;
  if (demo.status === 'failed') return `${said}: the Hub could not prepare the demo ${demo.slug} (${demo.lastError}).`;
  return null;
}

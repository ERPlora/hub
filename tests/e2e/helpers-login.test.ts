// @vitest-environment node
// flow: ninguno — e2e harness (hub#1317)
// `login()` (helpers.ts) when the SaaS's jump interrupts its `page.goto` to the hub. A spec that signs an owner up leaves
// the page on the SaaS's launcher, which opens the business it just made by itself once it is ready (the SaaS's
// LaunchPage.vue, «Opening by itself»): the hub's `/auth/login?next=/`, the SaaS's `/hub-login/` and back to the hub's
// `/`. When that falls while `login()` goes to the hub, Playwright throws «interrupted by another navigation», on the
// jump's way out to the SaaS or on its way back into the hub. That is the jump `login()` waits for anyway: it follows it
// and ends on `next`, also when the jump landed elsewhere. Any other error of `page.goto` fails it as before.
import type { Page } from '@playwright/test';
import { describe, expect, it } from 'vitest';

import { login, OWNER, SAAS } from './helpers';

const HUB = 'http://bar.localhost:8000';

/** Where the page is: its address, whether the hub's shell is up there and how many turns it stays before going on. */
interface Stop {
  url: string;
  shell?: boolean;
  stay?: number;
}

/** What one `page.goto` does: it throws `error` (or lands) and the page goes through `stops`, the first one where it
 *  is when `page.goto` settles (where it landed, or the navigation that interrupted it), one more each turn after. */
interface Goto {
  error?: Error;
  stops: Stop[];
}

/** The error Playwright throws when another navigation commits before the one `page.goto` started. */
const interrupted = (target: string, by: string): Error =>
  new Error(
    `page.goto: Navigation to "${target}" is interrupted by another navigation to "${by}"\n` +
      `Call log:\n  - navigating to "${target}", waiting until "load"\n`,
  );

/** A page whose `page.goto` calls do `gotos` in turn; each wait settles once the page is where it waits for, and fails
 *  as a timeout would some turns after the page stopped elsewhere. Turns of microtasks, never a timer: nothing is left
 *  armed when the test ends (vitest.setup.ts). No cookies: nothing is kept between logins. */
function pageDoing(gotos: Goto[]) {
  let at: Stop = { url: 'about:blank' };
  let ahead: Stop[] = [];
  const went: string[] = [];
  const walk = (): void => {
    if (ahead.length === 0) return;
    let stay = at.stay ?? 0;
    const go = (): void => {
      if (stay-- > 0) return queueMicrotask(go);
      at = ahead.shift() ?? at;
      walk();
    };
    queueMicrotask(go);
  };
  const until = (there: (stop: Stop) => boolean, what: string): Promise<void> =>
    new Promise((resolve, reject) => {
      const look = (patience: number): void => {
        if (there(at)) resolve();
        else if (patience === 0) reject(new Error(`${what}: Timeout 30000ms exceeded.`));
        else queueMicrotask(() => look(ahead.length > 0 ? patience : patience - 1));
      };
      look(10);
    });
  const page = {
    context: () => ({ cookies: async () => [], addCookies: async () => undefined }),
    async goto(url: string) {
      went.push(url);
      const doing = gotos.shift();
      if (!doing) throw new Error(`page.goto(${url}): not expected`);
      const [first, ...rest] = doing.stops;
      if (first) at = first;
      ahead = rest;
      walk();
      if (doing.error) throw doing.error;
      return null;
    },
    waitForURL: (url: string | ((url: URL) => boolean)) =>
      until((stop) => (typeof url === 'string' ? stop.url === url : url(new URL(stop.url))), 'page.waitForURL'),
    locator: () => ({ first: () => ({ waitFor: () => until((stop) => stop.shell === true, 'locator.waitFor') }) }),
    // The SaaS's sign-in form never shows: the account is signed in there, as the launcher's is.
    getByTestId: () => ({ waitFor: () => until(() => false, 'locator.waitFor') }),
    url: () => at.url,
  };
  return { page: page as unknown as Page, went };
}

const hubLogin = `${SAAS}/hub-login/?hub=bar&next=%2F&state=s`;
/** The SaaS's `/hub-login/` of the jump, which posts its code back to the hub a while later. */
const onTheSaas: Stop = { url: hubLogin, stay: 50 };

describe('login, when the SaaS’s jump interrupts its page.goto to the hub', () => {
  it.each([
    ['out to the SaaS', hubLogin, [onTheSaas, { url: `${HUB}/`, shell: true }]],
    ['back into the hub', `${HUB}/`, [{ url: `${HUB}/`, shell: true }]],
  ])('follows the jump on its way %s and ends on next in the hub', async (_way, by, stops) => {
    const { page, went } = pageDoing([{ error: interrupted(`${HUB}/`, by), stops }]);

    await login(page, HUB, '/', OWNER);

    expect(page.url()).toBe(`${HUB}/`);
    expect(went).toEqual([`${HUB}/`]);
  });

  it('goes on to next once in, when the jump landed elsewhere in the hub', async () => {
    const { page, went } = pageDoing([
      { error: interrupted(`${HUB}/apps`, hubLogin), stops: [onTheSaas, { url: `${HUB}/`, shell: true }] },
      { stops: [{ url: `${HUB}/apps`, shell: true }] },
    ]);

    await login(page, HUB, '/apps', OWNER);

    expect(page.url()).toBe(`${HUB}/apps`);
    expect(went).toEqual([`${HUB}/apps`, `${HUB}/apps`]);
  });
});

describe('login, when page.goto fails otherwise', () => {
  it.each([
    ['interrupted by a navigation that is not the jump (another origin)', interrupted(`${HUB}/`, 'http://other.localhost:8000/'), [{ url: 'http://other.localhost:8000/' }]],
    ['interrupted by a navigation to no address it can read', interrupted(`${HUB}/`, 'not an address'), []],
    [
      'a timeout',
      Object.assign(new Error(`page.goto: Timeout 30000ms exceeded.\nCall log:\n  - navigating to "${HUB}/", waiting until "load"\n`), {
        name: 'TimeoutError',
      }),
      [],
    ],
  ])('fails with that very error, at once: %s', async (_case, error, stops) => {
    const { page, went } = pageDoing([{ error, stops }]);

    await expect(login(page, HUB, '/', OWNER)).rejects.toBe(error);
    expect(went).toEqual([`${HUB}/`]);
  });
});

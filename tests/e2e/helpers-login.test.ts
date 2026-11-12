// @vitest-environment node
// flow: ninguno — e2e harness (hub#1317, hub#1342)
// `login()` (helpers.ts) against a fake page that runs on a clock of its own, so what it does over minutes takes no
// real time.
//
// The SaaS's jump interrupting its `page.goto` to the hub (hub#1317). A spec that signs an owner up leaves the page on
// the SaaS's launcher, which opens the business it just made by itself once it is ready (the SaaS's LaunchPage.vue,
// «Opening by itself»): the hub's `/auth/login?next=/`, the SaaS's `/hub-login/` and back to the hub's `/`. When that
// falls while `login()` goes to the hub, Playwright throws «interrupted by another navigation», on the jump's way out to
// the SaaS or on its way back into the hub. That is the jump `login()` waits for anyway: it follows it and ends on
// `next`, also when the jump landed elsewhere. Any other error of `page.goto` fails it as before.
//
// The hub's shell taking its time (hub#1342). On a loaded machine the SPA took more than the 30 s a step of the login
// waits (a sixth of the test's 180 s) to mount its shell, with nothing wrong. The shell is waited for as long as the
// test has, and what says it is not coming fails at once: the page threw, a script of it did not load, its document
// answered an error, or it went to an address that is neither the hub nor the SaaS.
import { type Page, type TestInfo, test } from '@playwright/test';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { login, OWNER, SAAS } from './helpers';

const HUB = 'http://bar.localhost:8000';
/** The config's time for a test (playwright.config.ts). */
const TEST_TIME = 180_000;
/** Later than a sixth of the test's time, the wait each step of the login had for the shell. */
const LATE = 45_000;
/** The page's own clock moves this much at each turn of microtasks. */
const TICK = 100;
/** Where the page's clock stops: a wait still on by then fails, so that a test never spins for ever. */
const CLOCK_END = 3_600_000;

/** Where the page is: its address, whether the hub's shell is up there, how long it stays before going on and how
 *  long its page takes to load (ms), and what happens as it arrives: its document answers `status` (with `headers`), the
 *  page throws `threw`, a script of it `script`, an iframe of it goes to `iframe`. */
interface Stop {
  url: string;
  shell?: boolean;
  for?: number;
  status?: number;
  headers?: Record<string, string>;
  threw?: string;
  script?: { status?: number; failure?: string };
  iframe?: string;
  loads?: number;
}

/** What one `page.goto` does: it throws `error` (or lands, its document answering `status`, 200 by default) and the
 *  page goes through `stops`, the first one where it is when `page.goto` settles (where it landed, or the navigation
 *  that interrupted it). */
interface Goto {
  error?: Error;
  status?: number;
  stops: Stop[];
}

/** The error Playwright throws when another navigation commits before the one `page.goto` started. */
const interrupted = (target: string, by: string): Error =>
  new Error(
    `page.goto: Navigation to "${target}" is interrupted by another navigation to "${by}"\n` +
      `Call log:\n  - navigating to "${target}", waiting until "load"\n`,
  );

/** Playwright's error for a wait that ran out. */
const timedOut = (what: string, timeout: number): Error =>
  Object.assign(new Error(`${what}: Timeout ${timeout}ms exceeded.`), { name: 'TimeoutError' });

type Listener = (payload: unknown) => void;

interface Waiter {
  there: (stop: Stop) => boolean;
  load: boolean;
  what: string;
  timeout: number;
  since: number;
  resolve: () => void;
  reject: (error: Error) => void;
}

/**
 * A page whose `page.goto` calls do `gotos` in turn. Its clock moves `TICK` ms at each turn of microtasks while it has
 * somewhere to go or something waits on it: a stop is left once its `for` is over, and each wait settles once the page
 * is where it waits for, or fails as Playwright's would once its `timeout` (0: none) is over. Microtasks, never a timer:
 * nothing is left armed when the test ends (vitest.setup.ts). No cookies: nothing is kept between logins.
 */
function pageDoing(gotos: Goto[]) {
  let now = 0;
  let at: Stop = { url: 'about:blank' };
  let leaves = 0;
  let loaded = 0;
  let ahead: Stop[] = [];
  let running = false;
  const went: string[] = [];
  const waiting = new Set<Waiter>();
  const listeners = new Map<string, Set<Listener>>();
  const mainFrame = { url: () => at.url };

  const emit = (event: string, payload: unknown): void => {
    for (const listener of [...(listeners.get(event) ?? [])]) listener(payload);
  };
  const request = (url: string, kind: 'document' | 'script', failure?: string) => ({
    url: () => url,
    resourceType: () => kind,
    isNavigationRequest: () => kind === 'document',
    frame: () => mainFrame,
    failure: () => (failure === undefined ? null : { errorText: failure }),
  });
  const response = (url: string, kind: 'document' | 'script', status: number, headers: Record<string, string> = {}) => ({
    url: () => url,
    status: () => status,
    headers: () => headers,
    ok: () => status < 400,
    request: () => request(url, kind),
  });
  const arrive = (stop: Stop, status = stop.status): void => {
    const moved = stop.url !== at.url;
    at = stop;
    leaves = now + (stop.for ?? 0);
    loaded = now + (stop.loads ?? 0);
    if (moved) emit('framenavigated', mainFrame);
    if (stop.iframe !== undefined) emit('framenavigated', { url: () => stop.iframe });
    if (status !== undefined) emit('response', response(stop.url, 'document', status, stop.headers));
    if (stop.script?.status !== undefined) emit('response', response(`${HUB}/static/main.js`, 'script', stop.script.status));
    if (stop.script?.failure !== undefined) emit('requestfailed', request(`${HUB}/static/main.js`, 'script', stop.script.failure));
    if (stop.threw !== undefined) emit('pageerror', new Error(stop.threw));
  };
  const settle = (waiter: Waiter): void => {
    if (waiter.there(at) && (!waiter.load || now >= loaded)) {
      waiting.delete(waiter);
      waiter.resolve();
    } else if (waiter.timeout > 0 && now >= waiter.since + waiter.timeout) {
      waiting.delete(waiter);
      waiter.reject(timedOut(waiter.what, waiter.timeout));
    } else if (now >= CLOCK_END) {
      waiting.delete(waiter);
      waiter.reject(new Error(`${waiter.what}: the fake page's clock stopped at ${CLOCK_END} ms with it still waiting`));
    }
  };
  const tick = (): void => {
    now += TICK;
    if (ahead.length > 0 && now >= leaves) arrive(ahead.shift() as Stop);
    for (const waiter of [...waiting]) settle(waiter);
    if (waiting.size > 0 || (ahead.length > 0 && now < CLOCK_END)) queueMicrotask(tick);
    else running = false;
  };
  const run = (): void => {
    if (running) return;
    running = true;
    queueMicrotask(tick);
  };
  const until = (there: (stop: Stop) => boolean, what: string, timeout = 30_000, load = false): Promise<void> =>
    new Promise((resolve, reject) => {
      waiting.add({ there, load, what, timeout, since: now, resolve, reject });
      run();
    });

  const page = {
    context: () => ({ cookies: async () => [], addCookies: async () => undefined }),
    async goto(url: string) {
      went.push(url);
      const doing = gotos.shift();
      if (!doing) throw new Error(`page.goto(${url}): not expected`);
      const [first, ...rest] = doing.stops;
      ahead = rest;
      if (first) arrive(first, doing.error ? first.status : (first.status ?? doing.status ?? 200));
      run();
      if (doing.error) throw doing.error;
      return response(at.url, 'document', doing.status ?? 200);
    },
    waitForURL: (url: string | ((url: URL) => boolean), options: { timeout?: number; waitUntil?: string } = {}) =>
      until(
        (stop) => (typeof url === 'string' ? stop.url === url : url(new URL(stop.url))),
        'page.waitForURL',
        options.timeout,
        (options.waitUntil ?? 'load') === 'load',
      ),
    locator: () => ({
      first: () => ({
        waitFor: (options: { timeout?: number } = {}) => until((stop) => stop.shell === true, 'locator.waitFor', options.timeout),
      }),
    }),
    // The SaaS's sign-in form never shows: the account is signed in there, as the launcher's is.
    getByTestId: () => ({ waitFor: (options: { timeout?: number } = {}) => until(() => false, 'locator.waitFor', options.timeout) }),
    url: () => at.url,
    mainFrame: () => mainFrame,
    on(event: string, listener: Listener) {
      listeners.set(event, (listeners.get(event) ?? new Set()).add(listener));
      return page;
    },
    off(event: string, listener: Listener) {
      listeners.get(event)?.delete(listener);
      return page;
    },
  };
  const listening = (): number => [...listeners.values()].reduce((count, set) => count + set.size, 0);
  return { page: page as unknown as Page, went, clock: () => now, listening };
}

/** `login()` run inside a Playwright test whose time is `timeout` ms, as `test.info()` tells it. */
function inATestOf(timeout: number): void {
  vi.spyOn(test, 'info').mockReturnValue({ timeout } as unknown as TestInfo);
}

afterEach(() => {
  vi.restoreAllMocks();
});

const hubLogin = `${SAAS}/hub-login/?hub=bar&next=%2F&state=s`;
/** The SaaS's `/hub-login/` of the jump, which posts its code back to the hub a while later. */
const onTheSaas: Stop = { url: hubLogin, for: 5_000 };

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

const target = `${HUB}/demo/items`;
/** The headers of the hub's pages of a business being prepared, under maintenance or with its database cut: a 503 whose
 *  meta refresh reloads it until the hub answers (base/templates/base/hub_preparing.html and its neighbours). */
const RELOADS_ITSELF = { 'retry-after': '10', 'content-type': 'text/html; charset=utf-8' };

/** What `login()` on `/demo/items` ends in: «signed in», or the error it threw, as text. */
const outcomeOf = (page: Page): Promise<string> =>
  login(page, HUB, '/demo/items', OWNER).then(
    () => 'signed in',
    (error: unknown) => String(error),
  );

describe('login, when the hub’s shell takes longer than a sixth of the test’s time to mount', () => {
  it.each([
    ['in a test of 180 s, with the hub’s session kept', TEST_TIME, [{ url: target, for: LATE }, { url: target, shell: true }]],
    ['outside a test, with the hub’s session kept', 0, [{ url: target, for: LATE }, { url: target, shell: true }]],
    ['in a test of 180 s, back from the SaaS', TEST_TIME, [onTheSaas, { url: target, for: LATE }, { url: target, shell: true }]],
    [
      'in a test of 180 s, through the 503 of a hub being prepared, which reloads by itself',
      TEST_TIME,
      [{ url: target, status: 503, headers: RELOADS_ITSELF, for: LATE }, { url: target, status: 200 }, { url: target, shell: true }],
    ],
  ])('waits for it and ends on next: %s', async (_case, testTime, stops) => {
    if (testTime > 0) inATestOf(testTime);
    const { page, went, clock, listening } = pageDoing([{ stops }]);

    await login(page, HUB, '/demo/items', OWNER);

    expect(page.url()).toBe(target);
    expect(went).toEqual([target]);
    expect(clock()).toBeGreaterThanOrEqual(LATE);
    expect(listening(), 'listeners left on the page').toBe(0);
  });

  it('fails saying the shell did not show up, once the test’s time is over, when it never mounts', async () => {
    inATestOf(TEST_TIME);
    const { page, clock, listening } = pageDoing([{ stops: [{ url: target }] }]);

    const failure = await outcomeOf(page);

    expect(failure).toMatch(new RegExp(`^Error: login on ${HUB}: .*the hub's shell .*${TEST_TIME} ms \\(at ${target}\\)$`));
    expect(clock()).toBeGreaterThanOrEqual(TEST_TIME);
    expect(listening(), 'listeners left on the page').toBe(0);
  });
});

describe('login, when the hub’s gate sends the page to the SaaS', () => {
  it('counts the SaaS’s own steps from the moment its page has loaded, as before', async () => {
    inATestOf(TEST_TIME);
    const { page } = pageDoing([
      { stops: [{ url: hubLogin, loads: 40_000, for: 50_000 }, { url: target, for: 1_000 }, { url: target, shell: true }] },
    ]);

    await login(page, HUB, '/demo/items', OWNER);

    expect(page.url()).toBe(target);
  });
});

describe('login, when the hub’s shell is not coming', () => {
  it.each([
    ['the page throws (its boot died)', { stops: [{ url: target, threw: 'boot exploded' }] }, 'boot exploded'],
    ['a script of the page is answered with an error', { stops: [{ url: target, script: { status: 500 } }] }, '500'],
    ['the hub answers its page with an error', { status: 503, stops: [{ url: target }] }, '503'],
    [
      'the hub answers its page with a 503 that never reloads (the plain text of a busy hub)',
      { stops: [{ url: target, status: 503, headers: { 'retry-after': '1', 'content-type': 'text/plain; charset=utf-8' } }] },
      'the hub answered 503',
    ],
    [
      'the hub answers its page with an error page without Retry-After (a 500)',
      { stops: [{ url: target, status: 500, headers: { 'content-type': 'text/html; charset=utf-8' } }] },
      'the hub answered 500',
    ],
    ['the hub sends its page to another address', { stops: [{ url: 'http://other.localhost:8000/there' }] }, 'went to http://other.localhost:8000/there'],
    [
      'the page goes to an address that is neither the hub nor the SaaS',
      { stops: [{ url: target, for: 1_000 }, { url: 'chrome-error://chromewebdata/' }] },
      'went to chrome-error://chromewebdata/',
    ],
    [
      'back from the SaaS, the hub sends the page to the SaaS again (it did not take the session)',
      { stops: [{ url: hubLogin, for: 1_000 }, { url: target, for: 1_000 }, { url: hubLogin }] },
      `went to ${hubLogin}`,
    ],
  ])('fails at once, saying why: %s', async (_case, goto: Goto, why) => {
    inATestOf(TEST_TIME);
    const { page, clock, listening } = pageDoing([goto]);

    const failure = await outcomeOf(page);

    expect(failure).toMatch(new RegExp(`^Error: login on ${HUB}: `));
    expect(failure).toContain(why);
    expect(clock(), 'failed within a few seconds of the page').toBeLessThan(5_000);
    expect(listening(), 'listeners left on the page').toBe(0);
  });

  it('a script that fails on the network (its dev server restarting) is a refused connection: one more try, which ends on next', async () => {
    inATestOf(TEST_TIME);
    const { page, went, listening } = pageDoing([
      { stops: [{ url: target, script: { failure: 'net::ERR_CONNECTION_REFUSED' } }] },
      { stops: [{ url: target, shell: true }] },
    ]);

    await login(page, HUB, '/demo/items', OWNER);

    expect(page.url()).toBe(target);
    expect(went).toEqual([target, target]);
    expect(listening(), 'listeners left on the page').toBe(0);
  });

  it('a script the jump aborts, an error thrown on the SaaS or an iframe gone elsewhere are not the hub’s: it waits for its shell', async () => {
    inATestOf(TEST_TIME);
    const { page } = pageDoing([
      {
        stops: [
          { url: target, script: { failure: 'net::ERR_ABORTED' }, for: 1_000 },
          { url: target, iframe: 'http://video.localhost:8000/embed', for: 1_000 },
          { ...onTheSaas, threw: 'the SaaS’s own' },
          { url: target, for: 1_000 },
          { url: target, shell: true },
        ],
      },
    ]);

    await login(page, HUB, '/demo/items', OWNER);

    expect(page.url()).toBe(target);
  });
});

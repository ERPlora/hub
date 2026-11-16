// @vitest-environment node
// flow: ninguno — e2e harness (hub#1317, hub#1342, hub#1370)
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
//
// The SaaS taking its time at a step of its sign-in (hub#1370): its form, its answer to the sign-in and the code form,
// its answer to the code and the way back to the hub. Each is waited for as long as the test has, and what says it is
// not coming fails at once: the SaaS's answer to the sign-in or to the code (turned down, failed, or a request that got
// no answer), a code asked for with no mail written, its document answering an error, or the page going elsewhere.
import { mkdirSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { type Page, type TestInfo, test } from '@playwright/test';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

// The folder the fake SaaS mails its codes to, which helpers.ts reads as it loads (`MAIL_DIR`). Hoisted above the
// imports, so no import is at hand here: the folder itself is made in `beforeAll`.
const MAIL = vi.hoisted(() => {
  const dir = `${(process.env.TMPDIR ?? '/tmp').replace(/\/?$/, '/')}helpers-login-mail-${process.pid}-${Date.now()}`;
  process.env.E2E_MAIL_DIR = dir;
  return dir;
});

import { login, OWNER, SAAS, SAAS_CODE, SAAS_SIGN_IN } from './helpers';

const HUB = 'http://bar.localhost:8000';
/** The config's time for a test (playwright.config.ts). */
const TEST_TIME = 180_000;
/** Later than a sixth of the test's time, the wait each step of the login had. */
const LATE = 45_000;
/** The page's own clock moves this much at each turn of microtasks. */
const TICK = 100;
/** Where the page's clock stops: a wait still on by then fails, so that a test never spins for ever. */
const CLOCK_END = 3_600_000;

/** Where the page is: its address, whether the hub's shell is up there, how long it stays before going on and how
 *  long its page takes to load (ms), and what happens as it arrives: its document answers `status` (with `headers`), the
 *  page throws `threw`, a script of it `script`, an iframe of it goes to `iframe`, the SaaS `answers`. On the SaaS, the
 *  `form` it shows, the `alert` under it, and `until`: the stop stays until that form is sent, and `for` counts from
 *  then. */
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
  form?: SaasForm;
  alert?: string;
  until?: SaasForm;
  answers?: Answer;
}

/** The SaaS's two forms of a password sign-in: the account (`/launch`) and the mailed code (`/verify-email`). */
type SaasForm = 'sign-in' | 'code';

/** The SaaS's answer to what its form posted: its `status` (with allauth's `errors`), or a request that got none
 *  (`failure`). With `mails`, the SaaS first mails that code to the owner, as it does before answering a sign-in. */
interface Answer {
  to: SaasForm;
  status?: number;
  errors?: string[];
  failure?: string;
  mails?: string;
}

/** Where each form of the SaaS posts. */
const POSTS_TO: Record<SaasForm, string> = { 'sign-in': SAAS_SIGN_IN, code: SAAS_CODE };

/** The line Django's file backend ends every mail with. */
const MAIL_END = '-'.repeat(79);
let mailed = 0;

/** A mail of the SaaS with `code` for the owner, written to its folder now, as its file backend does. */
function mailCode(code: string): void {
  mailed += 1;
  const message = `Subject: Your sign-in code\nTo: ${OWNER.email}\nContent-Transfer-Encoding: 7bit\n\n${code}\n`;
  writeFileSync(join(MAIL, `${Date.now()}-${mailed}.log`), `${message}${MAIL_END}\n`);
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
 * nothing is left armed when the test ends (vitest.setup.ts). No cookies: nothing is kept between logins. What `login()`
 * types is kept in `typed`, and which of the SaaS's forms it sent in `sent`.
 */
function pageDoing(gotos: Goto[]) {
  let now = 0;
  let at: Stop = { url: 'about:blank' };
  let leaves = 0;
  let loaded = 0;
  let ahead: Stop[] = [];
  let running = false;
  const went: string[] = [];
  const typed: string[] = [];
  const sent: SaasForm[] = [];
  const waiting = new Set<Waiter>();
  const listeners = new Map<string, Set<Listener>>();
  const mainFrame = { url: () => at.url };
  type Kind = 'document' | 'script' | 'fetch';
  type FakeResponse = ReturnType<typeof response>;
  /** Every answer of the SaaS to a form, in order: what `page.waitForResponse` looks through. */
  const answers: FakeResponse[] = [];

  const emit = (event: string, payload: unknown): void => {
    for (const listener of [...(listeners.get(event) ?? [])]) listener(payload);
  };
  const request = (url: string, kind: Kind, failure?: string) => ({
    url: () => url,
    method: () => (kind === 'fetch' ? 'POST' : 'GET'),
    resourceType: () => kind,
    isNavigationRequest: () => kind === 'document',
    frame: () => mainFrame,
    failure: () => (failure === undefined ? null : { errorText: failure }),
  });
  const response = (url: string, kind: Kind, status: number, headers: Record<string, string> = {}, body: unknown = {}) => ({
    url: () => url,
    status: () => status,
    headers: () => headers,
    ok: () => status < 400,
    request: () => request(url, kind),
    json: async () => body,
    text: async () => JSON.stringify(body),
  });
  const answer = ({ to, status = 200, errors, failure, mails }: Answer): void => {
    if (mails !== undefined) mailCode(mails);
    if (failure !== undefined) {
      emit('requestfailed', request(POSTS_TO[to], 'fetch', failure));
      return;
    }
    const body = errors ? { status, errors: errors.map((message) => ({ message })) } : { status, data: {} };
    const answered = response(POSTS_TO[to], 'fetch', status, { 'content-type': 'application/json' }, body);
    answers.push(answered);
    emit('response', answered);
  };
  const arrive = (stop: Stop, status = stop.status): void => {
    const moved = stop.url !== at.url;
    at = stop;
    leaves = stop.until ? Number.POSITIVE_INFINITY : now + (stop.for ?? 0);
    loaded = now + (stop.loads ?? 0);
    if (moved) emit('framenavigated', mainFrame);
    if (stop.iframe !== undefined) emit('framenavigated', { url: () => stop.iframe });
    if (status !== undefined) emit('response', response(stop.url, 'document', status, stop.headers));
    if (stop.script?.status !== undefined) emit('response', response(`${HUB}/static/main.js`, 'script', stop.script.status));
    if (stop.script?.failure !== undefined) emit('requestfailed', request(`${HUB}/static/main.js`, 'script', stop.script.failure));
    if (stop.threw !== undefined) emit('pageerror', new Error(stop.threw));
    if (stop.answers !== undefined) answer(stop.answers);
  };
  /** `form` sent: a stop that stays until then goes on `for` ms later. */
  const send = (form: SaasForm): void => {
    sent.push(form);
    if (at.until === form) leaves = now + (at.for ?? 0);
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
    waitForResponse: (match: (answered: FakeResponse) => boolean, options: { timeout?: number } = {}) => {
      const from = answers.length;
      const heard = (): FakeResponse | undefined => answers.slice(from).find(match);
      return until(() => heard() !== undefined, 'page.waitForResponse', options.timeout).then(() => heard() as FakeResponse);
    },
    // The hub's shell (`topbarApps`), and the alerts the SaaS shows under its form.
    locator: () => ({
      first: () => ({
        waitFor: (options: { timeout?: number } = {}) => until((stop) => stop.shell === true, 'locator.waitFor', options.timeout),
      }),
      allInnerTexts: async () => (at.alert === undefined ? [] : [at.alert]),
    }),
    // The SaaS's two forms, shown where a stop says so: their fields, their code input and their submit.
    getByTestId: (id: string) => {
      const form = ({ 'login-form': 'sign-in', 'verify-email-form': 'code' } as const)[id as 'login-form' | 'verify-email-form'];
      if (form === undefined) throw new Error(`getByTestId(${id}): not expected`);
      const input = { fill: async (value: string) => void typed.push(value) };
      return {
        waitFor: (options: { timeout?: number } = {}) => until((stop) => stop.form === form, 'locator.waitFor', options.timeout),
        getByTestId: () => ({ locator: () => input, click: async () => send(form) }),
        locator: () => ({ count: async () => 1, nth: () => input, first: () => input }),
      };
    },
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
  return { page: page as unknown as Page, went, typed, sent, clock: () => now, listening };
}

/** `login()` run inside a Playwright test whose time is `timeout` ms, as `test.info()` tells it. */
function inATestOf(timeout: number): void {
  vi.spyOn(test, 'info').mockReturnValue({ timeout } as unknown as TestInfo);
}

beforeAll(() => {
  mkdirSync(MAIL, { recursive: true });
});

afterEach(() => {
  vi.restoreAllMocks();
  // A mail left here would be within `MAIL_CLOCK_SLACK` of the next test's sign-in, and read as its own.
  for (const name of readdirSync(MAIL)) rmSync(join(MAIL, name));
});

afterAll(() => {
  rmSync(MAIL, { recursive: true, force: true });
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

/** `login()` on `/demo/items` in a test of 180 s, through `gotos`: its first try fails on the network, the second ends on next. */
async function endsOnNextAtTheSecondTry(gotos: Goto[]): Promise<void> {
  inATestOf(TEST_TIME);
  const { page, went, listening } = pageDoing(gotos);

  await login(page, HUB, '/demo/items', OWNER);

  expect(page.url()).toBe(target);
  expect(went).toEqual([target, target]);
  expect(listening(), 'listeners left on the page').toBe(0);
}

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
  it('waits for the SaaS however long its page takes to load, and for its way back to the hub', async () => {
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
    await endsOnNextAtTheSecondTry([
      { stops: [{ url: target, script: { failure: 'net::ERR_CONNECTION_REFUSED' } }] },
      { stops: [{ url: target, shell: true }] },
    ]);
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

const launch = `${SAAS}/launch?next=%2Fhub-login%2F`;
const verifyEmail = `${SAAS}/verify-email?next=%2Fhub-login%2F`;
/** The SaaS's `/hub-login/` once the account is signed in there: it posts its one-time code back to the hub. */
const handBack = `${SAAS}/hub-login/?hub=bar&next=%2Fdemo%2Fitems&state=s`;
/** The SaaS's page that says why it refused a sign-in or a jump to a hub: nothing goes on from there by itself. */
const refusedJump = (code: string): string => `${SAAS}/login/error?code=${code}`;
/** The code the fake SaaS mails at each sign-in. */
const MAILED = '424242';

/** The SaaS's steps of a sign-in with the form and the mailed code, in order. */
type SaasStep = 'form' | 'sign-in answer' | 'code form' | 'code answer' | 'way back';

/**
 * The trip through the SaaS's sign-in, each step coming `late[step]` ms after the one before (at once unless told), with
 * the SaaS answering the sign-in 401 (the mailed code pending, after mailing it) and the code 200 unless `answering`
 * says otherwise. `upTo` ends the trip there: the page stays on that step's stop.
 */
function signingIn(
  late: Partial<Record<SaasStep, number>> = {},
  answering: Partial<Record<SaasForm, Answer>> = {},
  upTo?: SaasStep,
): Stop[] {
  const steps: [SaasStep, Stop][] = [
    ['form', { url: launch, for: late.form ?? 0 }],
    ['sign-in answer', { url: launch, form: 'sign-in', until: 'sign-in', for: late['sign-in answer'] ?? 0 }],
    [
      'code form',
      {
        url: launch,
        form: 'sign-in',
        answers: answering['sign-in'] ?? { to: 'sign-in', status: 401, mails: MAILED },
        for: late['code form'] ?? 0,
      },
    ],
    ['code answer', { url: verifyEmail, form: 'code', until: 'code', for: late['code answer'] ?? 0 }],
    ['way back', { url: verifyEmail, form: 'code', answers: answering.code ?? { to: 'code', status: 200 } }],
  ];
  const end = upTo === undefined ? steps.length : steps.findIndex(([step]) => step === upTo) + 1;
  const trip = steps.slice(0, end).map(([, stop]) => stop);
  if (upTo !== undefined) return trip;
  return [...trip, { url: handBack, for: late['way back'] ?? 0 }, { url: target, for: 0 }, { url: target, shell: true }];
}

describe('login, when the SaaS takes longer than a sixth of the test’s time at one of its steps', () => {
  it.each([
    ['its sign-in form shows', signingIn({ form: LATE })],
    ['it answers the sign-in', signingIn({ 'sign-in answer': LATE })],
    ['its code form shows, once it has answered the sign-in', signingIn({ 'code form': LATE })],
    ['it answers the code', signingIn({ 'code answer': LATE })],
    ['the way back to the hub, once it has taken the code', signingIn({ 'way back': LATE })],
  ])('waits for it and signs in with the mailed code: %s', async (_case, stops) => {
    inATestOf(TEST_TIME);
    const { page, typed, sent, clock, listening } = pageDoing([{ stops }]);

    await login(page, HUB, '/demo/items', OWNER);

    expect(page.url()).toBe(target);
    expect(sent).toEqual(['sign-in', 'code']);
    expect(typed).toEqual([OWNER.email, OWNER.password, MAILED]);
    expect(clock()).toBeGreaterThanOrEqual(LATE);
    expect(listening(), 'listeners left on the page').toBe(0);
  });

  it.each([
    ['signed in there already, it sends the page back to the hub', [{ url: handBack, for: LATE }, { url: target }, { url: target, shell: true }]],
    [
      'on its sign-in page, signed in there already, it sends the page back to the hub without its form',
      [{ url: launch, for: LATE }, { url: target }, { url: target, shell: true }],
    ],
    [
      'back from the SaaS, the hub’s page takes its time to load',
      [{ url: launch, for: 1_000 }, { url: target, loads: LATE, for: LATE }, { url: target, shell: true }],
    ],
    [
      'it signs in without asking for a code and sends the page back to the hub',
      [
        ...signingIn({}, {}, 'sign-in answer'),
        { url: launch, form: 'sign-in', answers: { to: 'sign-in', status: 200 }, for: LATE } satisfies Stop,
        { url: handBack },
        { url: target },
        { url: target, shell: true },
      ],
    ],
  ])('waits for it and ends on next: %s', async (_case, stops: Stop[]) => {
    inATestOf(TEST_TIME);
    const { page, clock, listening } = pageDoing([{ stops }]);

    await login(page, HUB, '/demo/items', OWNER);

    expect(page.url()).toBe(target);
    expect(clock()).toBeGreaterThanOrEqual(LATE);
    expect(listening(), 'listeners left on the page').toBe(0);
  });
});

describe('login, when the SaaS says one of its steps is not coming', () => {
  const PASSWORD_MISMATCH = 'The email address and/or password you specified are not correct.';
  it.each([
    [
      'it turns the sign-in down',
      signingIn({}, { 'sign-in': { to: 'sign-in', status: 400, errors: [PASSWORD_MISMATCH] } }, 'code form'),
      `the SaaS turned the sign-in down, it answered 400: «${PASSWORD_MISMATCH}»`,
    ],
    ['it fails on the sign-in', signingIn({}, { 'sign-in': { to: 'sign-in', status: 500 } }, 'code form'), 'the SaaS failed on the sign-in, it answered 500'],
    ['it asks for the code without having mailed it', signingIn({}, { 'sign-in': { to: 'sign-in', status: 401 } }, 'code answer'), 'mail not found'],
    ['it fails on the code', signingIn({}, { code: { to: 'code', status: 500 } }, 'way back'), 'the SaaS failed on the code, it answered 500'],
    ['its page answers an error (a 500 on its /launch)', [{ url: launch, status: 500 }], `the SaaS answered 500 to ${launch}`],
    [
      'its page answers an error once it has taken the code (a 500 on its /hub-login/ on the way back)',
      [...signingIn({}, {}, 'way back'), { url: handBack, status: 500 }],
      `the SaaS answered 500 to ${handBack}`,
    ],
    [
      'it refuses the jump on its error page (the account is not a member of this hub)',
      [{ url: handBack, for: 1_000 }, { url: refusedJump('not_a_member') }],
      `the SaaS stopped the login on its error page ${refusedJump('not_a_member')}`,
    ],
    [
      'it refuses the jump on its error page once it has taken the code (too many jumps of the account)',
      [...signingIn({}, {}, 'way back'), { url: refusedJump('too_many') }],
      `the SaaS stopped the login on its error page ${refusedJump('too_many')}`,
    ],
    [
      'the page leaves the SaaS for an address that is neither it nor the hub (Chrome’s error page)',
      [{ url: launch, for: 1_000 }, { url: 'chrome-error://chromewebdata/' }],
      'went to chrome-error://chromewebdata/',
    ],
    [
      'the page leaves the SaaS for Chrome’s error page while it has the code',
      [...signingIn({}, {}, 'code answer'), { url: 'chrome-error://chromewebdata/' }],
      'went to chrome-error://chromewebdata/',
    ],
  ])('fails at once, saying so: %s', async (_case, stops: Stop[], why) => {
    inATestOf(TEST_TIME);
    const { page, clock, listening } = pageDoing([{ stops }]);

    const failure = await outcomeOf(page);

    expect(failure).toMatch(new RegExp(`^Error: login on ${HUB}: `));
    expect(failure).toContain(why);
    expect(failure).not.toContain('code rejected');
    expect(clock(), 'failed within a few seconds of the page').toBeLessThan(5_000);
    expect(listening(), 'listeners left on the page').toBe(0);
  });

  it('a code it turns down: «code rejected», with its answer and what it said, at once', async () => {
    inATestOf(TEST_TIME);
    const turnedDown: Stop = {
      url: verifyEmail,
      form: 'code',
      alert: 'Incorrect code.',
      answers: { to: 'code', status: 400, errors: ['Incorrect code.'] },
    };
    const { page, clock, listening } = pageDoing([{ stops: [...signingIn({}, {}, 'code answer'), turnedDown] }]);

    const failure = await outcomeOf(page);

    expect(failure).toBe(
      `Error: login on ${HUB}: code rejected, the SaaS answered 400 (code ${MAILED} for ${OWNER.email}, at ${verifyEmail}): «Incorrect code.»`,
    );
    expect(clock(), 'failed within a few seconds of the page').toBeLessThan(5_000);
    expect(listening(), 'listeners left on the page').toBe(0);
  });

  it.each([
    [
      'a code its request gets no answer to (the connection reset): it did not answer the code, not «code rejected»',
      // The SaaS's page says it could not sign in: an alert the SaaS did not answer, only its page wrote.
      [
        ...signingIn({}, {}, 'code answer'),
        {
          url: verifyEmail,
          form: 'code',
          alert: 'We could not sign you in. Please try again.',
          answers: { to: 'code', failure: 'net::ERR_CONNECTION_RESET' },
        } satisfies Stop,
      ],
      `^Error: login on ${HUB}: the SaaS did not answer the code \\(net::ERR_CONNECTION_RESET\\) \\(code ${MAILED} for ${OWNER.email}, at `,
    ],
    [
      'a sign-in its request gets no answer to (the connection refused): it did not answer the sign-in',
      [
        ...signingIn({}, {}, 'sign-in answer'),
        { url: launch, form: 'sign-in', answers: { to: 'sign-in', failure: 'net::ERR_CONNECTION_REFUSED' } } satisfies Stop,
      ],
      `^Error: login on ${HUB}: the SaaS did not answer the sign-in \\(net::ERR_CONNECTION_REFUSED\\)$`,
    ],
  ])('%s; one more try, which ends the same', async (_case, stops: Stop[], unanswered) => {
    inATestOf(TEST_TIME);
    const { page, went, clock, listening } = pageDoing([{ stops }, { stops }]);
    // When the first try fails, on the page's clock. Its wait for the answer stays on, as Playwright's does: on this
    // page's clock it runs out before the second try starts, so the clock at the end says nothing of the first try.
    const firstTryFailed: number[] = [];
    vi.spyOn(console, 'warn').mockImplementation(() => void firstTryFailed.push(clock()));

    const failure = await outcomeOf(page);

    expect(failure).toMatch(new RegExp(unanswered));
    expect(failure).not.toContain('code rejected');
    expect(went, 'one more try, from next again').toEqual([target, target]);
    expect(firstTryFailed).toHaveLength(1);
    expect(firstTryFailed[0], 'the first try failed within a few seconds of the page').toBeLessThan(5_000);
    expect(listening(), 'listeners left on the page').toBe(0);
  });

  it('a script of the SaaS answered with an error (its dev server optimizing it again, which reloads the page) is no sign: it signs in', async () => {
    inATestOf(TEST_TIME);
    const { page, went, listening } = pageDoing([{ stops: [{ url: launch, script: { status: 504 }, for: 1_000 }, ...signingIn()] }]);

    await login(page, HUB, '/demo/items', OWNER);

    expect(page.url()).toBe(target);
    expect(went).toEqual([target]);
    expect(listening(), 'listeners left on the page').toBe(0);
  });

  it('a script of the SaaS that fails on the network (its dev server restarting) is a refused connection: one more try, which signs in', async () => {
    await endsOnNextAtTheSecondTry([{ stops: [{ url: launch, script: { failure: 'net::ERR_CONNECTION_REFUSED' } }] }, { stops: signingIn() }]);
  });
});

describe('login, when the SaaS never answers the code', () => {
  it('fails saying the SaaS did not answer it, not «code rejected», once the test’s time is over', async () => {
    inATestOf(TEST_TIME);
    const { page, clock, listening } = pageDoing([{ stops: signingIn({}, {}, 'code answer') }]);

    const failure = await outcomeOf(page);

    expect(failure).toMatch(
      new RegExp(`^Error: login on ${HUB}: the SaaS did not answer the code within ${TEST_TIME} ms \\(code ${MAILED} for ${OWNER.email}, at `),
    );
    expect(failure).not.toContain('code rejected');
    expect(clock()).toBeGreaterThanOrEqual(TEST_TIME);
    expect(listening(), 'listeners left on the page').toBe(0);
  });
});

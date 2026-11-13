// Shared steps of the browser specs: the real login per host (Hub → SaaS → /auth/callback),
// the demo's API for setup, the list's readiness, the measurements file and the control of the dev
// server (runserver + Vite).
//
// The local hubs `a` and `b` answer only once they are rows of the registry (`base.Hub`): without them every
// host is a 404. `manage.py seed_local_hubs` (DEBUG only, idempotent) adds them;
// `database.ts` runs it on an e2e database and `global-setup.ts` checks it (`seed_local_hubs --check`) before
// the first spec. The shared `hub` database needs it once, by hand.
import { execSync, spawn } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  type Browser,
  type BrowserContext,
  type Cookie,
  expect,
  type Frame,
  type Locator,
  type Page,
  type Request as PageRequest,
  type Response as PageResponse,
  test,
} from '@playwright/test';

import { turnOffRecorded, turnOnRecording } from './apps-turned-on';
import { api } from './hub-api';
import { hubDatabases, plan } from './hub-databases';
import { mailDirFrom, readMailCode } from './mail';
import { withRetry } from './retry';
import { STACK } from './stack';

// The hub's API (setup and evidence), which every spec takes from here.
export { api };

export const A = STACK.hub('a');

/** The three sizes with the taller tablet, 834×1194. */
export const THREE_SIZES_TALL_TABLET = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** The three sizes the e2e looks at a screen in: a phone, a tablet and a desk. */
export const THREE_SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;
export const B = STACK.hub('b');

const HERE = dirname(fileURLToPath(import.meta.url));
export const HUB_DIR = join(HERE, '..', '..');
export const REPO_DIR = join(HUB_DIR, '..');
export const ARTIFACTS = join(HERE, '.artifacts');
const METRICS = join(ARTIFACTS, 'metrics');
const RUNSERVER_LOG = `/tmp/erplora-hub-runserver-${STACK.hubPort}.log`;

export interface Item {
  id: string;
  name: string;
  status: 'open' | 'done';
  note: string;
}

/** Every `ion-icon` on screen: its name and whether its shadow root painted an `<svg>`. */
export async function iconStates(page: Page): Promise<{ name: string; painted: boolean }[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll('ion-icon')]
      .filter((el) => el.getBoundingClientRect().width > 0)
      .map((el) => ({
        name: el.getAttribute('name') ?? '(icon prop)',
        painted: !!el.shadowRoot?.querySelector('svg'),
      })),
  );
}

/** How long `untilStill` waits for the page to stop moving: Ionic's overlays enter in well under a second. */
const STILL_TIMEOUT_MS = 10_000;

/**
 * What moves on the page now (run in the page, so self-contained): every finite animation running in the document
 * and in every open shadow root under it, however deep. `document.getAnimations()` leaves shadow roots out, and Ionic
 * animates its overlays (`ion-toast`, `ion-modal`, `ion-popover`), an `ion-progress-bar`'s bar or an `ion-segment`'s
 * indicator inside theirs. Endless ones (spinners, a shimmer) never stop, so they never count.
 */
function movingInPage(): string[] {
  const roots: Array<Document | ShadowRoot> = [document];
  const moving: string[] = [];
  for (const root of roots) {
    for (const element of root.querySelectorAll('*')) if (element.shadowRoot) roots.push(element.shadowRoot);
    for (const animation of root.getAnimations()) {
      if (animation.playState !== 'running' || animation.effect?.getTiming().iterations === Infinity) continue;
      const target = (animation.effect as KeyframeEffect | null)?.target;
      moving.push(`${root instanceof ShadowRoot ? `${root.host.localName} › ` : ''}${target?.localName ?? '?'}`);
    }
  }
  return moving;
}

/**
 * Puts `movingInPage` in the page as `window.__movingInPage`, for a probe that runs in the page frame by frame and has
 * to know, in the same frame, whether anything moves (the same detector as `untilStill`, never a copy of it).
 */
export async function exposeMovingInPage(page: Page): Promise<void> {
  await page.evaluate(`window.__movingInPage = ${movingInPage.toString()}`);
}

/** A page that navigates while `untilStill` asks what moves: it asks the new page next. Anything else fails the spec. */
function navigating(error: unknown): string[] {
  if (error instanceof Error && /Execution context was destroyed/.test(error.message)) return ['(navigating)'];
  throw error;
}

/**
 * Waits until nothing moves on screen (`movingInPage`): a capture taken mid-animation shows a state the screen is
 * leaving. A page that reloads meanwhile is asked again; one that still moves after `STILL_TIMEOUT_MS` fails the spec
 * with `message`, naming what moves.
 */
export async function untilStill(page: Page, message = 'untilStill(): still moving'): Promise<void> {
  await expect
    .poll(() => page.evaluate(movingInPage).catch(navigating), {
      message,
      timeout: STILL_TIMEOUT_MS,
      intervals: [16],
    })
    .toEqual([]);
}

/** Path of a screenshot under `.artifacts/` (created on demand). */
export function shot(name: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  return join(ARTIFACTS, `${name}.png`);
}

/** The fewest rows `repeatedTop` counts as a stripe. */
const STRIPE_MIN_ROWS = 8;

/**
 * How many rows at the bottom of `png`, a screenshot of `page`, repeat the first rows of the image: 0 when none. It is
 * what a capture taken before the browser painted the page at its new size shows (the area the resize uncovered,
 * filled with the top of the page): evidence of a screen nobody saw. A stripe whose rows are each one flat colour (a
 * background at both ends, a hairline across it) does not count, nor one that is the same row over and over, whatever
 * its colours across: a background crossed by a border (the assistant's panel, all the screen on a phone, with its left
 * border; a card's veil over it). The top of the page a capture before the paint repeats is its topbar, rows unlike
 * each other. Decoded in `page`'s browser: the e2e has no image library. Ported from erplora.com's e2e (`repeatedTop`
 * of its tests/e2e/panel/fixtures.ts).
 */
export async function repeatedTop(page: Page, png: Buffer): Promise<number> {
  return page.evaluate(
    async ({ base64, minRows }) => {
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const { width, height } = bitmap;
      const context = new OffscreenCanvas(width, height).getContext('2d');
      if (!context) throw new Error('repeatedTop: no 2d context to read the screenshot');
      context.drawImage(bitmap, 0, 0);
      const pixels = new Uint32Array(context.getImageData(0, 0, width, height).data.buffer);
      const sameRow = (a: number, b: number) => {
        for (let x = 0; x < width; x++) if (pixels[a * width + x] !== pixels[b * width + x]) return false;
        return true;
      };
      const flatRow = (row: number) => {
        for (let x = 1; x < width; x++) if (pixels[row * width + x] !== pixels[row * width]) return false;
        return true;
      };
      for (let rows = Math.floor(height / 2); rows >= minRows; rows--) {
        let repeated = true;
        let flat = true;
        let uniform = true;
        for (let row = 0; row < rows && repeated; row++) {
          repeated = sameRow(height - rows + row, row);
          flat &&= flatRow(row);
          uniform &&= sameRow(row, 0);
        }
        if (repeated && !flat && !uniform) return rows;
      }
      return 0;
    },
    { base64: png.toString('base64'), minRows: STRIPE_MIN_ROWS },
  );
}

/**
 * Resolves once the browser has painted the page as it is now: a frame's callbacks run before it is painted, the next
 * frame's once it has been. A screenshot right after `setViewportSize` needs it.
 */
export async function painted(page: Page): Promise<void> {
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))));
}

/**
 * Settled: nothing moving (`untilStill`: an overlay of Ionic entering included, endless spinners aside) and the page
 * painted as it is now (`painted`): the capture shows the state the flow reached, not a frame of Ionic's transition nor,
 * right after `setViewportSize`, the previous size's. The one wait of every spec (service-helpers.ts and
 * schedule-helpers.ts hand it out too).
 */
export async function settled(page: Page): Promise<void> {
  await untilStill(page);
  await painted(page);
}

/** How many times `scrolledTo` looks again for an element the page painted again while it scrolled to it. */
const SCROLL_REPAINTS = 10;

/** Playwright's error when the element an action took is gone from the page (painted again in its place). */
const notAttached = (error: unknown): boolean => error instanceof Error && error.message.includes('Element is not attached to the DOM');

/**
 * Scrolls to what `target` finds once it has stayed attached to the page through the scroll. Playwright's
 * `scrollIntoViewIfNeeded` takes the element once and keeps it (a click looks for it again; a scroll does not): right
 * after `page.setViewportSize`, a DataTable switches between its cards and its rows a frame or more later (its phone
 * breakpoint's `matchMedia`, #274), so a spec that checked the text in what the size before painted scrolls to an
 * element the list is replacing and fails with «Element is not attached to the DOM» (hub#1303). This looks for it
 * again, as many times as the page paints it again (up to `SCROLL_REPAINTS`, then it fails saying so); any other error
 * fails the spec as before.
 */
export async function scrolledTo(target: Locator): Promise<void> {
  for (let repaints = 0; repaints < SCROLL_REPAINTS; repaints++) {
    try {
      await target.scrollIntoViewIfNeeded();
      return;
    } catch (error) {
      if (!notAttached(error)) throw error;
    }
  }
  throw new Error(`scrolledTo: ${String(target)} was painted again ${SCROLL_REPAINTS} times while scrolling to it`);
}

/** How many screenshots `capture` takes at most while each one repeats the top of the page at its bottom. */
const CAPTURE_TRIES = 10;

/**
 * The screenshot of `page` as painted at its size, still, written as `.artifacts/<name>.png` and returned: every capture
 * of the e2e goes through here (`raw-screenshots.test.ts` keeps it so). It waits until nothing finite moves
 * (`untilStill`: an overlay of Ionic entering, endless spinners aside; one that still moves after its wait fails the
 * spec naming it, and nothing is written) and for a painted frame, and a screenshot that still repeats the top of the
 * page at its bottom (`repeatedTop`) is taken again, a frame later, up to `CAPTURE_TRIES` times; if every one does, it
 * fails saying so and writes nothing. What is on screen (data, a dialog) is the spec's to wait for before.
 */
export async function capture(page: Page, name: string, options: CaptureOptions = {}): Promise<Buffer> {
  let rows = 0;
  for (let tries = 0; tries < CAPTURE_TRIES; tries++) {
    await untilStill(page, `capture ${name}: still moving`);
    await painted(page);
    const png = await page.screenshot(options);
    rows = await repeatedTop(page, png);
    if (rows === 0) {
      writeFileSync(shot(name), png);
      return png;
    }
  }
  throw new Error(
    `capture ${name}: every screenshot repeats the top ${rows} rows of the page at its bottom (${CAPTURE_TRIES} tries): ` +
      'the browser never painted the page at its size',
  );
}

/** What `capture` hands to `page.screenshot`: everything but the path, which is `shot(name)`. */
export type CaptureOptions = Omit<NonNullable<Parameters<Page['screenshot']>[0]>, 'path'>;

/**
 * How many pixels of the page lie past the right edge of their box, 0 when everything fits its width: the document's
 * and, in every `ion-content` (the shown page's, the pinned side menu's, an open sheet's), its scroll box, in its shadow
 * root (`part="scroll"`; a hidden one is 0 wide). Ionic pins the `body` to the window, so a screen that runs past the
 * right edge is cut inside its `ion-content` and the document never grows: the document alone read 0 with a 1600 px
 * block on a page at 390. The one «no horizontal scroll» measure of the e2e (`horizontal-overflow.test.ts` keeps it so).
 */
export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const boxes: Element[] = [document.documentElement];
    for (const content of document.querySelectorAll('ion-content')) {
      const scroll = content.shadowRoot?.querySelector('[part~="scroll"]');
      if (scroll) boxes.push(scroll);
    }
    return Math.max(0, ...boxes.map((box) => box.scrollWidth - box.clientWidth));
  });
}

/** Writes the measurements of a check to `.artifacts/metrics/<key>.json` for the report. */
export function record(key: string, data: unknown): void {
  mkdirSync(METRICS, { recursive: true });
  writeFileSync(join(METRICS, `${key}.json`), `${JSON.stringify(data, null, 2)}\n`);
}

export const uniqueName = (prefix: string): string => `${prefix} ${Date.now().toString(36)}`;

/** The SaaS (`erplora.com` in production): the only login page a hub has. */
export const SAAS = STACK.saas;

/** «Upgrade plan» pressed in a browser with no session of erplora.com (BASE-F11): a tab of its own lands inside `a`'s
 *  plans by a pass, never on the sign-in form, and cannot reach back into the hub. */
export async function upgradeLandsInside(page: Page, link: Locator): Promise<void> {
  const context = page.context();
  // Only the SaaS's cookies (host `localhost`): the hub's session, on `a.localhost`, stays.
  await context.clearCookies({ domain: new URL(SAAS).hostname });
  const inside = `${SAAS}/dashboard/store/plans?business=${psql("SELECT id FROM base_hub WHERE slug = 'a'")}`;
  const passes: string[] = [];
  const seen = (request: { url(): string }) => {
    if (request.url().startsWith(`${SAAS}/hub-pass/?pass=`)) passes.push(request.url());
  };
  context.on('request', seen);
  const before = context.pages().length;
  const [tab] = await Promise.all([page.waitForEvent('popup'), link.click()]);
  await tab.waitForURL((url) => url.href.startsWith(inside));
  await expect(tab.getByTestId('store-plans')).toBeVisible();
  await expect(tab.getByTestId('login-form')).toHaveCount(0);
  expect(await tab.evaluate(() => window.opener), 'the new tab cannot reach back into the hub').toBeNull();
  expect(context.pages(), 'one tab, not two: the click did not also follow the link').toHaveLength(before + 1);
  expect(passes, 'through the door with one pass').toHaveLength(1);
  context.off('request', seen);
  await tab.close();
}
/**
 * Whether `page` is on the SaaS (its login): what its console says there is the SaaS's, judged by the SaaS's own
 * suite. Its headless API answers 401 while nobody is signed in (allauth's protocol), and Chrome logs each one.
 */
export const onSaas = (page: Page): boolean => new URL(page.url()).origin === SAAS;
/** A SaaS account: what its sign-in page asks for. */
export interface Credentials {
  email: string;
  password: string;
}
/** The demo customer account in the SaaS (`saas … demo_seed`): owner of hubs `a` and `b`. */
export const OWNER: Credentials = { email: 'owner@example.com', password: 'owner' };
/** The demo employee in the SaaS (`demo_seed`): `hub_employee` of `a` and `b`, views Demo only. */
export const EMPLOYEE: Credentials = { email: 'employee@example.com', password: 'employee' };
/** Where the local SaaS writes its mails (Django's file backend): `saas/.mail` beside the Hub, or `E2E_MAIL_DIR`. */
export const MAIL_DIR = mailDirFrom(process.env, REPO_DIR);
/** Slack between our clock and the mail file's modification time, in ms. */
export const MAIL_CLOCK_SLACK = 50;
/** What each wait of `login` lasts outside a test, or in one with no time limit, in ms: the config's test time. */
const LOGIN_DEFAULT = 180_000;
/** Where the SaaS's sign-in form posts the account (allauth.headless). */
export const SAAS_SIGN_IN = `${SAAS}/_allauth/browser/v1/auth/login`;
/** Where the SaaS's code form posts the code it mailed (allauth.headless). */
export const SAAS_CODE = `${SAAS}/_allauth/browser/v1/auth/code/confirm`;

/** The running test's (or hook's) time limit, in ms; 0 outside a test or hook, as with no limit. */
function runningTimeout(): number {
  try {
    return test.info().timeout;
  } catch {
    // `test.info()` throws outside a test or a hook: there is no time limit to follow.
    return 0;
  }
}

/**
 * How long each wait of `login` lasts, in ms: the running test's whole time (`LOGIN_DEFAULT` outside a test or in one
 * with no limit), never a share of it. Every step comes as fast as the machine runs: on a loaded one the SPA took more
 * than a sixth of the config's 180 s to mount the hub's shell (hub#1342), and the SaaS as long to answer the sign-in or
 * the code (hub#1370), with nothing wrong. What says a step is not coming fails at once instead (`watchTrip`,
 * `shellOrSaas`, `alongTheTrip`); a step that never comes, without any of that, runs into the test's own limit, which
 * then names its wait.
 */
function loginTimeout(): number {
  return runningTimeout() || LOGIN_DEFAULT;
}

/**
 * The SaaS's cookies of each account this worker signed in, by address. Every sign-in at the SaaS is one more
 * open session of the account, and allauth walks them all at the next one (`allauth.usersessions`): with a
 * session left by every login, the SaaS took 30 and 37 s to answer the code on a loaded machine (hub#107, 1680
 * sessions of the owner). A later login in a fresh context starts with them, as a person signed in at
 * erplora.com: the SaaS skips its form and its code.
 */
const saasSessions = new Map<string, Cookie[]>();

/** Django's session cookie, the Hub's and the SaaS's (`SESSION_COOKIE_NAME`, left at its default by both). */
const SESSION_COOKIE = 'sessionid';
/**
 * A hub's cookies that a browser coming back to it still has: its session and the language the jump set
 * (`LANGUAGE_COOKIE_NAME`, the Hub's default). Not its `csrftoken`, which the SPA's page sets in every context.
 */
const HUB_SESSION_COOKIES = new Set([SESSION_COOKIE, 'django_language']);

/**
 * The hub's session of each account this worker signed in, by account and hub (`hubSessionKey`). Every jump to a
 * hub is one more for the SaaS's brake (`HUB_LOGIN_RATELIMIT`, 20 per account every 5 minutes, ACCOUNTS-F28): a
 * spec of more than 20 logins, each in a fresh context, fell at the 21st with «429 · Too many attempts»
 * (staff-flows.spec.ts). A later login in a fresh context starts with it and lands on `next` with no jump, as a
 * person who comes back to their business.
 */
const hubSessions = new Map<string, Cookie[]>();

const hubSessionKey = (account: string, origin: string): string => `${account} ${origin}`;

/**
 * The hub's session cookies of `origin` in `context`: only its host's own. The SaaS's (host `localhost`) come
 * along in `context.cookies(origin)` too, and are never a hub's.
 */
async function hubSessionOf(context: BrowserContext, origin: string): Promise<Cookie[]> {
  const host = new URL(origin).hostname;
  return (await context.cookies(origin)).filter((c) => c.domain === host && HUB_SESSION_COOKIES.has(c.name));
}

/**
 * The real login of a hub: `origin + next` → the SPA's gate sends to the SaaS (`/hub-login/?hub=…`)
 * → the SaaS asks for the account at `/launch` (or, signed in there already, skips it) → every
 * password sign-in then waits at `/verify-email` for the code the SaaS mails to the account
 * (`ACCOUNT_LOGIN_BY_CODE_REQUIRED`), read from the local SaaS's mail folder (`MAIL_DIR`) → it
 * follows its `next` (`/hub-login/…`), which POSTs a one-time code to `origin/auth/callback` → the Hub
 * opens its session and lands on `next`. The account is `credentials` (the owner unless told otherwise).
 *
 * An account signs in to the SaaS once per worker: a fresh context then starts with that SaaS session
 * (`saasSessions`) and only the hub's half of the trip runs. A context that has been to the SaaS keeps what
 * it has there. When that session has ended (a spec signed out at the SaaS), the SaaS asks for the account
 * again and the new session is the one kept.
 *
 * The same with the hub: the session a jump opened for the account is kept for that hub (`hubSessions`), and a
 * fresh context starts with it and lands on `next` without going through the SaaS, so a spec jumps once per
 * account and hub while that session lives. When it has ended (a spec signed out of the hub), the hub sends to
 * the SaaS as always and the new session is the one kept. A context that already has a session of the hub keeps
 * it. Only a session the SaaS opened for `credentials` is kept: one signed in with the form, or with the account's
 * own SaaS session in a context that had none. `fresh: true` jumps through the SaaS even with a kept session (a
 * spec about the jump itself), and keeps the session it opens.
 *
 * It ends on `next` itself, once the hub's shell is up, the same on the jump as with a kept session: `next` is a
 * page, never a route the SPA's router redirects (`/inventory` → `/inventory/dashboard`), which fails at once
 * saying where it landed. Looking earlier on the jump let such a `next` pass alone and time out after other specs.
 *
 * A page left on the SaaS's launcher (`signUpOnSaas`) may jump into the business by itself: the launcher opens the
 * one it just made once it is ready (the SaaS's `LaunchPage.vue`, «Opening by itself»), and when that falls while
 * `page.goto` is on its way, Playwright throws «interrupted by another navigation», on the jump's way out to the SaaS
 * or on its way back into the hub (`interruptedByTheJump`, hub#1317). That is the jump this login waits for anyway:
 * it follows it and, back in the hub, goes on to `next` if the jump landed elsewhere (the launcher's lands on `/`).
 * Any other error of `page.goto` fails it as before.
 *
 * Every step is waited for as long as the test has (`loginTimeout`): the hub's shell, on the way in and at the end,
 * and each step at the SaaS (its sign-in page or the way back, its answer to the sign-in, its code form, its answer to
 * the code, the way back to the hub); a loaded machine may take any of it. What says a step is not coming fails at once,
 * saying why: on the hub, the page threw; on the hub or the SaaS, one of its scripts did not load or its document
 * answered an error (`watchTrip`); the page went to an address that is neither this hub nor the SaaS (`shellOrSaas`,
 * `alongTheTrip`); the SaaS turned down or failed the sign-in or the code, or one of them got no answer at all; the SaaS
 * asked for the code without a mail with it (`signInWithCode`).
 *
 * runserver or the SaaS restarting (another session saved a `.py` file) refuses the connection for
 * a moment: the trip through the SaaS then starts again once, a second later (`withRetry`). From
 * `origin + next` again, because a POST that died leaves Chrome's error page, with no form to
 * submit; if the SaaS did sign in, the second trip skips its form, and if it did not, signing in
 * again mails a new code, the one read then.
 */
export async function login(
  page: Page,
  origin: string,
  next = '/demo/items',
  credentials: Credentials = OWNER,
  options: { fresh?: boolean } = {},
): Promise<void> {
  const target = `${origin}${next}`;
  const timeout = loginTimeout();
  const context = page.context();
  const account = credentials.email.toLowerCase();
  const kept = saasSessions.get(account);
  // A context with no SaaS cookies goes to the SaaS as this account, never as another one.
  const ownSaas = (await context.cookies(SAAS)).length === 0;
  if (kept && ownSaas) await context.addCookies(kept);
  const hubSession = async () => (await hubSessionOf(context, origin)).find((c) => c.name === SESSION_COOKIE)?.value;
  const keptHub = options.fresh ? undefined : hubSessions.get(hubSessionKey(account, origin));
  if (keptHub && (await hubSession()) === undefined) await context.addCookies(keptHub);
  // What the hub had before the trip: a jump replaces it. `where` cannot tell, the whole jump may happen
  // within `page.goto` (the gate sends to the SaaS before the page's load).
  const before = await hubSession();
  let signedIn = false;
  const trip = watchTrip(page, origin);
  try {
    await withRetry(
      async () => {
        trip.restart();
        const jumped = await goneOrJumped(page, target, origin);
        const where = await shellOrSaas(page, origin, trip, { orSaas: true });
        if (where === 'saas') {
          const neither = `the SaaS showed neither its sign-in form nor the hub within ${timeout} ms`;
          // Its sign-in page (`/launch`) or already the hub, one wait at a time: a wait that lost a race would stay
          // pending for the rest of the test, and might be the one Playwright names when the test's time runs out.
          const inHub = (url: URL): boolean => url.origin === origin;
          const atSignIn = (url: URL): boolean => url.origin === SAAS && url.pathname === '/launch';
          await alongTheTrip(page, origin, trip, page.waitForURL((url) => inHub(url) || atSignIn(url), { timeout }), {
            timedOut: () => neither,
          });
          if (!inHub(new URL(page.url()))) {
            const step = await alongTheTrip(page, origin, trip, page.getByTestId('login-form').waitFor({ state: 'visible', timeout }), {
              back: inHub,
              timedOut: () => neither,
            });
            if (step !== 'back') {
              await signInWithCode(page, origin, credentials, trip, timeout);
              signedIn = true;
            }
          }
          // Back from the SaaS: the hub's callback sends to `next`. In the hub already, the shell is up and the
          // address final (checked below): waiting for `next` there waited for an address that might never come.
          // The jump that cut `page.goto` short sends to its own `next`: back in the hub is all it gives.
          await alongTheTrip(page, origin, trip, page.waitForURL(jumped ? inHub : target, { timeout }), {
            timedOut: () => `back from the SaaS, ${jumped ? 'the hub' : target} did not come within ${timeout} ms (at ${page.url()})`,
          });
        }
        // In with the session that jump opened, wherever it landed: on to `next`.
        if (jumped && !sameAddress(page.url(), target)) await page.goto(target);
      },
      {
        onRetry: (error) =>
          console.warn(`login on ${origin}: ${String(error).split('\n')[0]}; trying once more in 1 s`),
      },
    );
    await shellOrSaas(page, origin, trip);
  } finally {
    trip.stop();
  }
  if (signedIn) saasSessions.set(account, await context.cookies(SAAS));
  const opened = await hubSession();
  if (opened !== undefined && opened !== before && (signedIn || ownSaas)) {
    hubSessions.set(hubSessionKey(account, origin), await hubSessionOf(context, origin));
  }
  // Only now is the address final: the SPA mounts its shell once its router has settled, redirects included
  // (`router.isReady()`, frontend/main.ts). Back from the SaaS, the wait above saw `next` as its document arrived.
  const landed = page.url();
  if (!sameAddress(landed, target)) {
    throw new Error(`login on ${origin}: landed on ${landed}, not on ${target}: the SPA's router took \`next\` elsewhere`);
  }
}

/** Whether two addresses are the same once written the same way (`http://a.localhost:8000` and `…:8000/`). */
const sameAddress = (one: string, other: string): boolean => new URL(one).href === new URL(other).href;

/** Playwright's error when another navigation commits before the one `page.goto` started: where that one went. */
const INTERRUPTED = /is interrupted by another navigation to "([^"]+)"/;

/**
 * Whether `error` is a `page.goto` to the hub at `origin` cut short by the SaaS's jump: another navigation committed
 * first, on the jump's way out to the SaaS or on its way back into this hub. Not one to anywhere else, nor any other
 * error.
 */
function interruptedByTheJump(error: unknown, origin: string): boolean {
  const to = error instanceof Error ? INTERRUPTED.exec(error.message)?.[1] : undefined;
  if (to === undefined || !URL.canParse(to)) return false;
  const where = new URL(to).origin;
  return where === new URL(SAAS).origin || where === new URL(origin).origin;
}

/** `page.goto(target)`; `true` when the SaaS's jump cut it short (`interruptedByTheJump`), any other error thrown. */
async function goneOrJumped(page: Page, target: string, origin: string): Promise<boolean> {
  try {
    await page.goto(target);
    return false;
  } catch (error) {
    if (!interruptedByTheJump(error, origin)) throw error;
    return true;
  }
}

/** Chromium's failure of a request the page itself dropped, as it does with what is loading when it navigates away. */
const ABORTED = 'net::ERR_ABORTED';

/**
 * Whether the hub's answer to a page is one that reloads by itself until the hub answers: the pages of a business being
 * prepared, under maintenance or with its database cut are HTML with `Retry-After` and a meta refresh
 * (`base/templates/base/hub_preparing.html` and its neighbours). The plain text of a busy hub never reloads.
 */
const reloadsItself = (response: PageResponse): boolean => {
  const headers = response.headers();
  return headers['retry-after'] !== undefined && (headers['content-type'] ?? '').startsWith('text/html');
};

/** What `watchTrip` gives `login`: the first sign it saw that the trip will not get to the hub's shell. */
interface TripWatch {
  /** Rejects with that sign, at once if it came already; never settles while none comes. */
  failed(): Promise<never>;
  /** Forgets the sign seen so far: another try of the trip starts over. */
  restart(): void;
  /** Stops listening to the page. */
  stop(): void;
}

/** The site of the trip `url` is on: the hub at `origin`, the SaaS, or neither. */
function siteOf(url: string, origin: string): 'hub' | 'saas' | undefined {
  const where = URL.canParse(url) ? new URL(url).origin : '';
  if (where === origin) return 'hub';
  return where === SAAS ? 'saas' : undefined;
}

/**
 * Listens to `page` for what says the login on the hub at `origin` will not get to its shell, while `login` runs. On the
 * hub: the page threw (`pageerror`: its boot died), one of its scripts did not load (it failed, or was answered with an
 * error: the SPA never starts), or its document was answered with an error that does not reload by itself (a 500, the
 * 503 of a busy hub; not `reloadsItself`). On the SaaS: its document was answered with an error, or one of its scripts
 * failed on the network (its SPA never starts either). Not an error the SaaS's page throws, nor a script of the SaaS
 * answered with an error (its dev server answers 504 to a dependency it has just optimized again, and the page reloads
 * by itself), nor, anywhere, a script the page drops itself as it navigates away (`ABORTED`).
 */
function watchTrip(page: Page, origin: string): TripWatch {
  let seen: Error | undefined;
  let tell: ((error: Error) => void) | undefined;
  const saw = (why: string, site: 'hub' | 'saas'): void => {
    if (seen) return;
    const so = site === 'hub' ? "so the hub's shell will not show up" : 'so the SaaS will not send the page back to the hub';
    seen = new Error(`login on ${origin}: ${why}, ${so}`);
    tell?.(seen);
  };
  const at = () => siteOf(page.url(), origin);
  const threw = (error: Error): void => {
    if (at() === 'hub') saw(`the page threw «${error.message}» at ${page.url()}`, 'hub');
  };
  const answered = (response: PageResponse): void => {
    const request = response.request();
    if (response.status() < 400) return;
    if (request.isNavigationRequest()) {
      const site = siteOf(response.url(), origin);
      if (request.frame() === page.mainFrame() && site !== undefined && !reloadsItself(response)) {
        saw(`the ${site === 'hub' ? 'hub' : 'SaaS'} answered ${response.status()} to ${response.url()}`, site);
      }
    } else if (request.resourceType() === 'script' && at() === 'hub') {
      saw(`a script of ${page.url()} was answered ${response.status()} (${response.url()})`, 'hub');
    }
  };
  const dropped = (request: PageRequest): void => {
    const failure = request.failure()?.errorText;
    const site = at();
    if (request.resourceType() !== 'script' || failure === undefined || failure === ABORTED || site === undefined) return;
    saw(`a script of ${page.url()} did not load, ${failure} (${request.url()})`, site);
  };
  page.on('pageerror', threw);
  page.on('response', answered);
  page.on('requestfailed', dropped);
  return {
    failed: () =>
      new Promise<never>((_, reject) => {
        if (seen) reject(seen);
        else tell = reject;
      }),
    restart: () => {
      seen = undefined;
      tell = undefined;
    },
    stop: () => {
      page.off('pageerror', threw);
      page.off('response', answered);
      page.off('requestfailed', dropped);
    },
  };
}

/** Playwright's error for a wait that ran out of time. */
const isTimeout = (error: unknown): boolean => error instanceof Error && error.name === 'TimeoutError';

/**
 * Waits for the hub at `origin` to mount its shell in `page` (`topbarApps` attached): `'hub'`. With `orSaas`, the
 * SaaS is an answer too, as soon as the page is there (`'saas'`: the hub's gate sent it there to sign in). It waits
 * as long as the test has (`loginTimeout`), and fails at once on what says the shell is not coming: what `trip` saw, or
 * the page at an address that is neither this hub nor, with `orSaas`, the SaaS (Chrome's error page among them).
 *
 * Where the page goes is followed by listening (`framenavigated`), never by another wait of Playwright's: the shell's
 * is the one pending, so when the test's time runs out first it is the one Playwright names (it names a pending
 * `page.waitForURL` before a locator's wait).
 */
async function shellOrSaas(
  page: Page,
  origin: string,
  trip: TripWatch,
  options: { orSaas?: boolean } = {},
): Promise<'hub' | 'saas'> {
  const timeout = loginTimeout();
  let went: (url: string) => void = () => undefined;
  const onSaas = new Promise<'saas'>((resolve, reject) => {
    went = (url) => {
      const site = siteOf(url, origin);
      if (options.orSaas && site === 'saas') resolve('saas');
      else if (site !== 'hub') {
        reject(new Error(`login on ${origin}: the page went to ${url}, which is not this hub, so its shell will not show up`));
      }
    };
  });
  const followed = (frame: Frame): void => {
    if (frame === page.mainFrame()) went(frame.url());
  };
  page.on('framenavigated', followed);
  went(page.url());
  try {
    const shell = topbarApps(page)
      .waitFor({ state: 'attached', timeout })
      .then(
        () => 'hub' as const,
        (error: unknown) => {
          if (!isTimeout(error)) throw error;
          const what = options.orSaas ? "neither the SaaS nor the hub's shell" : "the hub's shell";
          throw new Error(`login on ${origin}: ${what} showed up within ${timeout} ms (at ${page.url()})`);
        },
      );
    return await Promise.race([trip.failed(), onSaas, shell]);
  } finally {
    page.off('framenavigated', followed);
  }
}

/** What a step of the trip through the SaaS needs besides its wait (`alongTheTrip`). */
interface Along {
  /** What it fails with when its wait runs out of its own time (outside a test, or in one with no limit). */
  timedOut: () => string;
  /** Rejects with what says the step is not coming. */
  refused?: Promise<never>;
}

/**
 * One step of the trip through the SaaS: `step`, the one wait of Playwright's pending while it runs, so that when the
 * test's time runs out first it is the one Playwright names; with `back`, the page arriving at an address `back` takes
 * ends it too (`'back'`). It waits as long as `step` does, and fails at once on what says the step is not coming: what
 * `trip` saw, `refused`, or the page at an address that is neither this hub nor the SaaS (Chrome's error page among
 * them).
 */
async function alongTheTrip<T>(page: Page, origin: string, trip: TripWatch, step: Promise<T>, options: Along): Promise<T>;
async function alongTheTrip<T>(
  page: Page,
  origin: string,
  trip: TripWatch,
  step: Promise<T>,
  options: Along & { back: (url: URL) => boolean },
): Promise<T | 'back'>;
async function alongTheTrip<T>(
  page: Page,
  origin: string,
  trip: TripWatch,
  step: Promise<T>,
  options: Along & { back?: (url: URL) => boolean },
): Promise<T | 'back'> {
  let leave = (): void => undefined;
  const moved = new Promise<'back'>((resolve, reject) => {
    const went = (url: string): void => {
      if (URL.canParse(url) && options.back?.(new URL(url))) resolve('back');
      else if (siteOf(url, origin) === undefined) {
        reject(new Error(`login on ${origin}: the page went to ${url}, which is neither this hub nor the SaaS, so the login will not get back`));
      }
    };
    const followed = (frame: Frame): void => {
      if (frame === page.mainFrame()) went(frame.url());
    };
    page.on('framenavigated', followed);
    leave = () => page.off('framenavigated', followed);
    went(page.url());
  });
  const waited = step.catch((error: unknown) => {
    throw isTimeout(error) ? new Error(`login on ${origin}: ${options.timedOut()}`) : error;
  });
  try {
    return await Promise.race([waited, moved, trip.failed(), ...(options.refused ? [options.refused] : [])]);
  } finally {
    leave();
  }
}

/**
 * The SaaS's answer to what the page posts to `url` from now on, taken before the post goes: `answered` is Playwright's
 * wait for it, and `dropped` rejects with `unanswered(failure)` when the post gets no answer at all (its request failed:
 * the SaaS dropped the connection or refused it). Neither is left unhandled when the login fails before waiting on them.
 */
function answerTo(page: Page, url: string, timeout: number, unanswered: (failure: string) => Error) {
  const posted = (request: PageRequest): boolean => request.method() === 'POST' && request.url() === url;
  const answered = page.waitForResponse((response) => posted(response.request()), { timeout });
  let stop = (): void => undefined;
  const dropped = new Promise<never>((_, reject) => {
    const failed = (request: PageRequest): void => {
      if (posted(request)) reject(unanswered(request.failure()?.errorText ?? 'no answer'));
    };
    page.on('requestfailed', failed);
    stop = () => page.off('requestfailed', failed);
  });
  answered.catch(() => undefined);
  dropped.catch(() => undefined);
  return { answered, dropped, stop };
}

/** What the SaaS said in its answer (allauth's `errors`), as `: «…»` for an error message; nothing if it said nothing. */
async function saidIn(response: PageResponse): Promise<string> {
  const body: unknown = await response.json().catch(() => undefined);
  const errors = (body as { errors?: { message?: unknown }[] } | undefined)?.errors ?? [];
  const text = errors
    .map((error) => (typeof error.message === 'string' ? error.message.trim() : ''))
    .filter(Boolean)
    .join(' / ');
  return text ? `: «${text}»` : '';
}

/**
 * The SaaS's sign-in form (`/launch`) and then, when the SaaS asks for it, the code it mailed (`/verify-email`); done
 * once the SaaS has taken the code, or signed in without one. Each step goes on the SaaS's own answer. To the sign-in,
 * a 401 asks for the code (allauth: the mailed code pending) and a 2xx signs in; to the code, a 2xx takes it. Any other
 * answer fails at once with what the SaaS said: a 4xx is the SaaS turning it down («code rejected» for the code), a 5xx
 * the SaaS failing on it. A post that gets no answer at all (dropped, refused) fails at once too, as the network error it
 * is, which `login` tries again; one still waiting when the test's time runs out is the wait Playwright names. The mail
 * with the code is read once, when the code form shows: the SaaS writes it before it answers the sign-in.
 */
async function signInWithCode(
  page: Page,
  origin: string,
  credentials: Credentials,
  trip: TripWatch,
  timeout: number,
): Promise<void> {
  const form = page.getByTestId('login-form');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  // Taken before the submit: the mail is written while the SaaS answers it.
  const since = Date.now() - MAIL_CLOCK_SLACK;
  const signIn = answerTo(page, SAAS_SIGN_IN, timeout, (failure) => new Error(`login on ${origin}: the SaaS did not answer the sign-in (${failure})`));
  let signedIn: PageResponse;
  try {
    await form.getByTestId('login-submit').click();
    signedIn = await alongTheTrip(page, origin, trip, signIn.answered, {
      refused: signIn.dropped,
      timedOut: () => `sign-in form sent, but the SaaS did not answer it within ${timeout} ms`,
    });
  } finally {
    signIn.stop();
  }
  const status = signedIn.status();
  if (status >= 500) throw new Error(`login on ${origin}: the SaaS failed on the sign-in, it answered ${status}${await saidIn(signedIn)}`);
  if (status >= 400 && status !== 401) {
    throw new Error(`login on ${origin}: the SaaS turned the sign-in down, it answered ${status}${await saidIn(signedIn)}`);
  }
  if (status !== 401) return;

  const codeForm = page.getByTestId('verify-email-form');
  await alongTheTrip(page, origin, trip, codeForm.waitFor({ state: 'visible', timeout }), {
    timedOut: () => `the SaaS asked for the code, but /verify-email did not come within ${timeout} ms (at ${page.url()})`,
  });
  // The SaaS mails the code before it answers the sign-in: not there now, it never will be.
  const code = await readMailCode({ dir: MAIL_DIR, to: credentials.email, since, timeout: 0 }).catch((error: unknown) => {
    throw new Error(
      `login on ${origin}: mail not found, though the SaaS asked for the code it mails before answering the sign-in: ${error instanceof Error ? error.message : String(error)}`,
    );
  });
  // `CodeField` is one input today; six one-digit inputs would take a digit each.
  const inputs = codeForm.locator('input:not([type=hidden])');
  const count = await inputs.count();
  if (count >= code.length) {
    for (const [i, digit] of [...code].entries()) await inputs.nth(i).fill(digit);
  } else {
    await inputs.first().fill(code);
  }
  const which = () => `(code ${code} for ${credentials.email}, at ${page.url()})`;
  const taken = answerTo(page, SAAS_CODE, timeout, (failure) => new Error(`login on ${origin}: the SaaS did not answer the code (${failure}) ${which()}`));
  let answer: PageResponse;
  try {
    await codeForm.getByTestId('verify-email-submit').click();
    answer = await alongTheTrip(page, origin, trip, taken.answered, {
      refused: taken.dropped,
      timedOut: () => `the SaaS did not answer the code within ${timeout} ms ${which()}`,
    });
  } finally {
    taken.stop();
  }
  if (answer.status() >= 500) {
    throw new Error(`login on ${origin}: the SaaS failed on the code, it answered ${answer.status()} ${which()}${await saidIn(answer)}`);
  }
  if (answer.status() >= 400) {
    throw new Error(`login on ${origin}: code rejected, the SaaS answered ${answer.status()} ${which()}${await saidIn(answer)}`);
  }
}

/**
 * A new browser context logged in on `origin` (as the owner unless `credentials`), first page on `next`; with
 * `fresh`, through the SaaS even when `login` keeps a session of the hub.
 */
export async function hostPage(
  browser: Browser,
  origin: string,
  options: { next?: string; viewport?: { width: number; height: number }; credentials?: Credentials; fresh?: boolean } = {},
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: origin, viewport: options.viewport });
  const page = await context.newPage();
  await login(page, origin, options.next, options.credentials, { fresh: options.fresh });
  return { context, page };
}

/** The owner of `a` on `next`, with the Hub in Spanish (its language cookie, as the language picker leaves it). */
export async function signedInSpanish(
  browser: Browser,
  viewport: { width: number; height: number },
  next: string,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, next);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  // A reload, not a goto: the login already left the page on `next`, and a goto to the same address with a hash
  // would not load it again.
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return { context, page };
}

/** Saves the owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked. */
export async function saveSessionForTheSweep(context: BrowserContext): Promise<void> {
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
}

/** The capture once the screen settled and nothing scrolls sideways. */
export async function settledCapture(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

/** What the page on screen marks with this `data-testid`. */
export const testid = (page: Page, id: string): Locator => shown(page).locator(`[data-testid="${id}"]`);

/** `id`'s row in the Apps screen. */
export const appRow = (page: Page, id: string): Locator => shown(page).locator(`[data-testid="apps-row"][data-id="${id}"]`);

/** The names the topbar's «My apps» (the menu of the apps, from the session) lists now. */
export async function menuApps(page: Page): Promise<string[]> {
  await testid(page, 'topbar-apps').click();
  const sheet = page.locator('[data-testid="apps-launcher"]').last();
  const tiles = sheet.locator('[data-testid="apps-launcher-app"]');
  await expect(tiles.first()).toBeVisible();
  const names = (await tiles.allInnerTexts()).map((name) => name.trim());
  await sheet.locator('[data-testid="apps-launcher-close"]').click();
  await expect(sheet).toBeHidden();
  return names;
}

export async function createItem(context: BrowserContext, origin: string, name: string): Promise<Item> {
  const res = await api<Item>(context, origin, 'POST', '/demo/items', { name });
  expect(res.status, `create ${name}`).toBe(201);
  return res.data;
}

export async function itemDetail(
  context: BrowserContext,
  origin: string,
  id: string,
): Promise<Item & { lines: { text: string; client_line_id: string | null }[] }> {
  const res = await api<Item & { lines: { text: string; client_line_id: string | null }[] }>(
    context,
    origin,
    'GET',
    `/demo/items/detail?id=${id}`,
  );
  expect(res.status).toBe(200);
  return res.data;
}

/** What a template brings, last first (tables before their zones, products before their categories), each with
 * the operation's route that lists it and the one that takes a row away: the server's own (`base.blueprint`). */
const TEMPLATE_DATA = [
  ['/table/tables', '/table/tables/delete'],
  ['/table/zones', '/table/zones/delete'],
  ['/service/services', '/service/services/archive'],
  ['/service/categories', '/service/categories/delete'],
  ['/inventory/products', '/inventory/products/delete'],
  ['/inventory/categories', '/inventory/categories/delete'],
] as const;

/**
 * Takes away every row a template brings from the business at `origin`, through the apps' operations (their apps
 * on), until the server says the business is empty.
 */
export async function emptyOfTemplateData(context: BrowserContext, origin: string): Promise<void> {
  for (let pass = 0; pass < 5; pass += 1) {
    for (const [list, remove] of TEMPLATE_DATA) {
      const rows = await api<{ rows: { id: string }[] }>(context, origin, 'GET', `${list}?limit=100&offset=0`);
      expect(rows.status, list).toBe(200);
      for (const row of rows.data.rows) {
        const res = await api(context, origin, 'POST', remove, { id: row.id });
        expect(res.status, `${remove} ${row.id}`).toBeLessThan(300);
      }
    }
    const catalogue = await api<{ empty: boolean }>(context, origin, 'GET', '/settings/data/blueprints');
    if (catalogue.data.empty) return;
  }
  throw new Error('the business could not be emptied of what a template brings');
}

/** How long the run's worker may take to make an app's tables in a business's own database: its tick, the
 *  migrations of the app and what it needs, and its settle. */
export const APP_SET_UP_MS = 60_000;

/**
 * Turns on `apps` in the business at `origin`, as the person of `context` who runs it, through Apps' own command
 * (`POST /api/apps/enable`, `base.app.enable`): a business is born with every app off.
 * One already on changes nothing. In a business whose own database lacks an app's tables (a demo, a new business)
 * the answer is 202 «creating» and the run's worker makes them: it waits until `base.app.list` says it is on.
 */
export async function turnOn(context: BrowserContext, origin: string, ...apps: string[]): Promise<void> {
  for (const app of apps) {
    const answer = await api<{ state: string }>(context, origin, 'POST', '/apps/enable', { app });
    const said = `turn on ${app}: ${answer.status} ${JSON.stringify(answer.data)}`;
    expect([200, 202], said).toContain(answer.status);
    if (answer.status === 202) {
      expect(answer.data.state, said).toBe('creating');
      await expect
        .poll(
          async () => {
            const listed = await api<{ apps: { id: string; state: string }[] }>(context, origin, 'GET', '/apps');
            return listed.data.apps.find((row) => row.id === app)?.state;
          },
          { message: `${app} set up by the worker`, timeout: APP_SET_UP_MS },
        )
        .toBe('on');
    }
  }
}

/**
 * Turns on, in their order, the apps of `needed` that are off in the business at `origin` (`turnOn`), and appends each
 * to `turnedOn` once it is on: the record a spec file's `afterAll` hands to `turnOffTurnedOn`, so it turns off what
 * this file turned on and nothing else. Called from a `beforeAll`, after whatever may fall first (the check of the
 * SaaS's assistant provider): a file that fell before turning anything on leaves the business as it found it (hub#480).
 */
export async function turnOnMissing(context: BrowserContext, origin: string, needed: readonly string[], turnedOn: string[]): Promise<void> {
  const listed = await api<{ apps: { id: string; state: string }[] }>(context, origin, 'GET', '/apps');
  expect(listed.status, `list the apps: ${JSON.stringify(listed.data)}`).toBe(200);
  const on = new Set(listed.data.apps.filter((app) => app.state === 'on').map((app) => app.id));
  await turnOnRecording(needed, on, (app) => turnOn(context, origin, app), turnedOn);
}

/** Turns off, last first, what `turnOnMissing` recorded in `turnedOn`, through Apps' own command
 *  (`POST /api/apps/disable`, `base.app.disable`): nothing when nothing was turned on (hub#480). */
export async function turnOffTurnedOn(context: BrowserContext, origin: string, turnedOn: string[]): Promise<void> {
  await turnOffRecorded(turnedOn, async (app) => {
    const off = await api(context, origin, 'POST', '/apps/disable', { app });
    expect(off.status, `turn off ${app}: ${JSON.stringify(off.data)}`).toBe(200);
  });
}

/** Deletes every demo item, through the API. */
export async function clearItems(context: BrowserContext, origin: string): Promise<number> {
  let deleted = 0;
  for (;;) {
    const page = await api<{ rows: { id: string }[] }>(context, origin, 'GET', '/demo/items?limit=100');
    if (page.data.rows.length === 0) return deleted;
    for (const row of page.data.rows) {
      const res = await api(context, origin, 'POST', '/demo/items/delete', { id: row.id });
      expect(res.status).toBeLessThan(300);
      deleted += 1;
    }
  }
}

/** Ionic's overlays. An inline `ion-modal` wraps its content in an `.ion-page` of its own. */
const OVERLAYS = 'ion-modal, ion-popover, ion-alert, ion-action-sheet, ion-loading, ion-toast, ion-picker-legacy';

/**
 * The page shown by `IonRouterOutlet` (hidden pages stay in the DOM), never a dialog presented over it:
 * Ionic moves a presented modal to `ion-app`, after the pages, so the last visible `.ion-page` would be the
 * dialog's. A dialog is found with `page.locator('ion-modal[data-testid=…]')`, not here.
 */
export const shown = (page: Page): Locator =>
  page.locator(`.ion-page:not(.ion-page-hidden):not(:is(${OVERLAYS}) *)`).last();

/**
 * The ⠿ «My apps» button of the hub's topbar (its sidebar): there once the
 * authenticated shell is painted (every page of the stack has its own; the first one is enough).
 */
export const topbarApps = (page: Page): Locator => page.locator('[data-testid=topbar-apps]').first();

/**
 * Opens the «My apps» sheet from the screen on view and returns it. Ionic moves a presented modal to
 * `ion-app`, outside the page, so it is found on the page (the presented one), not in `shown(page)`.
 */
export async function openApps(page: Page): Promise<Locator> {
  await shown(page).locator('[data-testid=topbar-apps]').click();
  const sheet = page.locator('ion-modal[data-testid=apps-launcher]:not(.overlay-hidden)');
  await expect(sheet.locator('[data-testid=apps-launcher-app]').first()).toBeVisible();
  return sheet;
}

/** Whether the page is a phone's (under 768 px): base folds the assistant's sparkles and the bell into «More options». */
export const compactBar = (page: Page): boolean => (page.viewportSize()?.width ?? 1280) < 768;

/** The bell's count on the screen on view: on the bell, or on a phone's «More options», which carries it. */
export const bellBadge = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid=topbar-chrome-more-badge]' : '[data-testid=hub-bell] [data-testid=hub-bell-badge]');

/** The bell's count says `total`, or shows nothing when it is 0. */
export async function badgeSays(page: Page, total: number, options: { timeout?: number } = {}): Promise<void> {
  if (total > 0) await expect(bellBadge(page)).toHaveText(String(total), options);
  else await expect(bellBadge(page)).toHaveCount(0, options);
}

/** The page still, with nothing past its right edge at the size `label`, then captured as `name`. */
export async function capturedFitting(page: Page, name: string, label: string): Promise<void> {
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `no sideways scroll at ${label}`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

/**
 * Opens the bell's list (BASE-F10) and resolves once it is presented: the bell itself, or on a phone its row in «More
 * options» (TopbarChrome.vue). Ionic animates a popover in a shadow root, so it waits for its `ionPopoverDidPresent`.
 */
export async function openBell(page: Page): Promise<void> {
  const presented = page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const done = (event: Event) => {
          if (!(event.target as Element).querySelector('[data-testid^="hub-bell-"]')) return;
          document.removeEventListener('ionPopoverDidPresent', done);
          resolve();
        };
        document.addEventListener('ionPopoverDidPresent', done);
      }),
  );
  if (compactBar(page)) {
    await shown(page).locator('[data-testid=topbar-chrome-more]').click();
    await page.locator('ion-popover [data-testid=topbar-chrome-more-bell]').click();
  } else {
    await shown(page).locator('[data-testid=hub-bell]').click();
  }
  await presented;
}

/** Waits until the list painted its first result (empty state or rows). */
export async function listReady(page: Page): Promise<void> {
  await shown(page)
    .locator('[data-testid=demo-items-empty], [data-testid=demo-items-row]')
    .first()
    .waitFor({ state: 'visible' });
}

export async function rowNames(page: Page): Promise<string[]> {
  return shown(page).locator('[data-testid=demo-item-name]').allInnerTexts();
}

export const row = (page: Page, name: string): Locator =>
  shown(page).locator('[data-testid=demo-items-row]', { has: page.getByText(name, { exact: true }) });

/** The row (or card) of the item `id` on the list shown. */
export const rowOf = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=demo-items-row][data-id="${id}"]`);

/** From the list: «New item» → `/demo/items/new`, types the name and arms a click-time probe on
 *  «Save» (not clicked yet): `__saveClickedAt` (`Date.now()`) and `__saveClickedPageMs` (`performance.now()`, the
 *  page's clock, which Resource Timing uses). */
export async function fillNewItem(page: Page, name: string): Promise<Locator> {
  await shown(page).locator('[data-testid=demo-items-add]').click();
  await page.waitForURL(/\/demo\/items\/new$/);
  const form = shown(page).locator('[data-testid=demo-form]');
  await form.locator('[data-testid=demo-form-name] input').fill(name);
  const save = form.locator('[data-testid=demo-form-save]');
  await save.evaluate((el) => {
    const w = window as unknown as Record<string, number>;
    el.addEventListener(
      'click',
      () => {
        w.__saveClickedAt = Date.now();
        w.__saveClickedPageMs = performance.now();
      },
      { capture: true, once: true },
    );
  });
  return save;
}

/** Creates an item through the «New item» page and waits until it is back on the list. */
export async function createViaPage(page: Page, name: string): Promise<void> {
  const save = await fillNewItem(page, name);
  await save.click();
  await page.waitForURL(/\/demo\/items$/, { timeout: 10_000 });
  await listReady(page);
}

/** In-page probe: the `Date.now()` at which a row named `name` shows up (read by `appearedAt`). */
export async function watchForRow(page: Page, name: string): Promise<void> {
  await page.evaluate((wanted) => {
    const w = window as unknown as { __rowSeen?: Record<string, number> };
    w.__rowSeen ??= {};
    const seen = w.__rowSeen;
    const check = (): boolean => {
      const found = [...document.querySelectorAll('[data-testid=demo-item-name]')].some(
        (el) => el.textContent?.trim() === wanted,
      );
      if (found && seen[wanted] === undefined) seen[wanted] = Date.now();
      return found;
    };
    if (check()) return;
    const observer = new MutationObserver(() => {
      if (check()) observer.disconnect();
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  }, name);
}

export async function appearedAt(page: Page, name: string): Promise<number | undefined> {
  return page.evaluate((wanted) => (window as unknown as { __rowSeen?: Record<string, number> }).__rowSeen?.[wanted], name);
}

/** Collects CSP violations (in-page listener), console errors and uncaught page errors. */
export async function collectProblems(
  page: Page,
): Promise<() => Promise<{ csp: unknown[]; console: string[]; warnings: string[]; page: string[] }>> {
  const consoleErrors: string[] = [];
  const warnings: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (msg) => {
    if (onSaas(page)) return;
    if (msg.type() === 'error') consoleErrors.push(msg.text());
    if (msg.type() === 'warning') warnings.push(msg.text());
  });
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: unknown[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      w.__csp.push({ directive: e.violatedDirective, blocked: e.blockedURI, sample: e.sample, source: e.sourceFile });
    });
  });
  return async () => ({
    csp: await page.evaluate(() => (window as unknown as { __csp?: unknown[] }).__csp ?? []),
    console: consoleErrors,
    warnings,
    page: pageErrors,
  });
}

// ── Dev server control ──────────────────────────────────────────────────────────────────────────

/** Pids LISTENING on a TCP port (never the browser's client sockets). */
export function listeningPids(port: number): number[] {
  try {
    return execSync(`lsof -ti tcp:${port} -sTCP:LISTEN`, { encoding: 'utf8' })
      .split(/\s+/)
      .filter(Boolean)
      .map(Number);
  } catch {
    return [];
  }
}

export async function healthy(): Promise<boolean> {
  try {
    const res = await fetch(STACK.healthz, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * runserver's Vite (`pnpm run dev` in hub-next) answers. It starts after Django: `healthy()` alone
 * lets a page load HTML whose module scripts point at a Vite that is not listening yet, and that page
 * stays blank (nothing retries a failed module script).
 */
export async function viteReady(): Promise<boolean> {
  try {
    const res = await fetch(STACK.viteClient, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function waitFor(check: () => Promise<boolean> | boolean, timeoutMs: number, stepMs = 250): Promise<number> {
  const start = Date.now();
  for (;;) {
    if (await check()) return Date.now() - start;
    if (Date.now() - start > timeoutMs) throw new Error(`condition not met within ${timeoutMs} ms`);
    await new Promise((r) => setTimeout(r, stepMs));
  }
}

/**
 * Starts `manage.py runserver 127.0.0.1:<E2E_HUB_PORT>` detached (it outlives the test run), with this
 * run's environment (`VITE_DEV_PORT`, `SAAS_URL`, `DB_NAME`).
 */
export function startRunserver(): void {
  const child = spawn(
    '/bin/bash',
    ['-c', `cd '${HUB_DIR}' && nohup uv run python manage.py runserver 127.0.0.1:${STACK.hubPort} >> ${RUNSERVER_LOG} 2>&1 &`],
    { detached: true, stdio: 'ignore' },
  );
  child.unref();
}

/**
 * Rows of `pg_stat_activity` named `live-listener` (the process-level LISTEN connection) on this run's
 * database: another stack beside it (another checkout's runserver) has its own.
 */
export function listenerRows(): { pid: number; backend_start: string }[] {
  const out = execSync(
    `docker compose exec -T postgres psql -U hub -d ${STACK.database} -At -F '|' -c "select pid, backend_start from pg_stat_activity where application_name='live-listener' and datname = current_database() order by pid"`,
    { cwd: REPO_DIR, encoding: 'utf8' },
  );
  return out
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const [pid, start] = line.split('|');
      return { pid: Number(pid), backend_start: start };
    });
}

/** `sql` on the database `database` of compose's Postgres, as its superuser `hub`. */
function psqlOn(database: string, sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${database} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** Each hub's own database, from the stack's registry (read once per hub; one that shares control's is control's). */
const hubDatabase = hubDatabases(STACK.database, (sql) => psqlOn(STACK.database, sql));

/** Where each scratch table of this run's specs was made (`hub-databases.ts`), kept between calls. */
const scratchTables = new Map<string, string>();

/** The database the scratch table `table` is in, control's or `hub`'s, when this process never noted it: Playwright
 * starts a new worker process after a failed test, and a spec's `afterAll` there must still find its copy. */
function scratchTableOf(table: string, hub: string): string | undefined {
  return [STACK.database, hubDatabase(hub)].find(
    (database) => psqlOn(database, `select to_regclass('\\"${table}\\"') is not null`) === 't',
  );
}

/** `sql` where its tables live (`hub-databases.ts`): each statement on control's tables in the stack's control
 * database, on any other in `hub`'s own (`a` unless the spec names another), the
 * ones in a row on one database in one call; what they print, in order. A statement that names both is refused. */
export function psql(sql: string, hub = 'a'): string {
  return plan(sql, hub, STACK.database, hubDatabase, scratchTables, (table) => scratchTableOf(table, hub))
    .map((run) => psqlOn(run.database, run.sql))
    .filter(Boolean)
    .join('\n');
}

/**
 * The username of whoever is signed in on `context`. Not by email: a hub database kept from a stack whose SaaS was
 * created again holds an older account with the same email (a new SaaS, new users), and the email names both.
 */
export async function usernameOf(context: BrowserContext): Promise<string> {
  const me = await api<{ user: { id: string } | null }>(context, A, 'GET', '/me');
  expect(me.status, 'GET /api/me').toBe(200);
  const id = me.data.user?.id ?? '';
  expect(id, 'the person signed in').not.toBe('');
  // `/api/me` names the person of the business's database (base.HubUser), whose username is the session's.
  return psql(`SELECT username FROM base_hubuser WHERE id = '${id}'`);
}

/** The usernames of every account of `email` (control's ``auth_user``), quoted for the `in (…)` of a statement on a
 * hub's tables, which cannot read control's; `null` when it has none, which matches nothing. */
export function usernamesOf(email: string): string {
  return psql(`select string_agg(quote_literal(username), ',') from auth_user where email = '${email}'`) || 'null';
}

/** The person (``base.HubUser``) of the account `email` in `hub`'s database: its username is control's (``auth_user``),
 * the person the hub's; '' when it has none yet. */
export function hubUserIdOf(email: string, hub = 'a'): string {
  return psql(`select id from base_hubuser where username in (${usernamesOf(email)})`, hub);
}

/** Takes the plan out of `a`'s photo while a spec runs, keeping the photo in its scratch table `backup` (next to the
 * registry) for `restorePhotoFrom`: for a spec that signs in from more than one browser. With a plan in the photo
 * (erplora.com's Free covers one device, as its seed or a run of the WhatsApp specs can leave it), every entry from
 * another browser ends the sessions of the others on `a`, and the next request of the first gets a 401. */
export function dropPlanFromPhoto(backup: string): void {
  psql(`drop table if exists ${backup}; create table ${backup} as select id, state from base_hub where slug = 'a'`);
  psql("update base_hub set state = state - 'plan' where slug = 'a'");
}

/** `a`'s photo as `dropPlanFromPhoto` found it, and its scratch table `backup` dropped; nothing when it kept none. */
export function restorePhotoFrom(backup: string): void {
  if (psql(`select to_regclass('${backup}') is not null`) !== 't') return;
  psql(`update base_hub h set state = b.state from ${backup} b where b.id = h.id; drop table ${backup}`);
}

/** Decodes the `s=` of a `/api/live` URL (base64url JSON) into its subscriptions. */
export function decodeSubs(url: string): unknown[] {
  const s = new URL(url).searchParams.get('s') ?? '';
  const json = Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
  try {
    const value: unknown = JSON.parse(json);
    return Array.isArray(value) ? value : [value];
  } catch {
    return [json];
  }
}

// ── The business's registration (flow business-currency) ──────────────────────────────────────────

/** The secret `/internal` is signed with; the local default of both projects. */
const INTERNAL_SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';

/** `PUT <path>` on the Hub's `/internal` door, with `body` signed the way erplora.com signs it. */
export async function internalPut(path: string, body: string): Promise<Response> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', INTERNAL_SECRET).update(`${timestamp}.${body}`).digest('hex');
  return fetch(`http://127.0.0.1:${STACK.hubPort}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
}

/** A hub's registration as erplora.com sent it (`base_hub`): read before a run moves its business, put back after. */
export interface Registration {
  id: string;
  slug: string;
  name: string;
  country: string;
  timezone: string;
  language: string;
  vertical: string | null;
}

/** The registration of the hub `slug` as the run finds it. */
export function registrationOf(slug: string): Registration {
  const [id, name, country, timezone, language, vertical] = psql(
    `select id, name, country, timezone, language, coalesce(vertical, '') from base_hub where slug = '${slug}'`,
  ).split('|');
  return { id, slug, name, country, timezone, language, vertical: vertical || null };
}

/** erplora.com registers `registration`'s business in `country`, the way the SaaS does (`PUT /internal/hubs/{id}`,
 *  signed): its currency is then its country's. */
export async function registerBusinessIn(registration: Registration, country: string): Promise<void> {
  const response = await internalPut(`/internal/hubs/${registration.id}`, JSON.stringify({ ...registration, country }));
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(psql(`select country from base_hub where slug = '${registration.slug}'`)).toBe(country);
}

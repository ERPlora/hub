// Shared steps of the browser PoC (plan §8): the real login per host (Hub → SaaS → /auth/callback),
// the demo's API for setup, the list's readiness, the measurements file and the control of the dev
// server (runserver + Vite).
//
// The local hubs `a` and `b` answer only once they are rows of the registry (`base.Hub`): without them every
// host is a 404 (plan 2026-10-17, §1.3). `manage.py seed_local_hubs` (DEBUG only, idempotent) adds them;
// `database.ts` runs it on an e2e database and `global-setup.ts` checks it (`seed_local_hubs --check`) before
// the first spec. The shared `hub` database needs it once, by hand.
import { execSync, spawn } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Browser, type BrowserContext, type Cookie, expect, type Locator, type Page, test } from '@playwright/test';

import { mailDirFrom, readMailCode } from './mail';
import { isConnectionRefused, withRetry } from './retry';
import { STACK } from './stack';

export const A = STACK.hub('a');
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
/** The PoC's customer account in the SaaS (`saas … demo_seed`): owner of hubs `a` and `b`. */
export const OWNER: Credentials = { email: 'owner@example.com', password: 'owner' };
/** The PoC's employee in the SaaS (`demo_seed`): `hub_employee` of `a` and `b`, views Demo only. */
export const EMPLOYEE: Credentials = { email: 'employee@example.com', password: 'employee' };
/** Where the local SaaS writes its mails (Django's file backend): `saas/.mail` beside the Hub, or `E2E_MAIL_DIR`. */
export const MAIL_DIR = mailDirFrom(process.env, REPO_DIR);
/** Slack between our clock and the mail file's modification time, in ms. */
const MAIL_CLOCK_SLACK = 50;
/** What each step of `login` waits outside a test, or in one with no time limit, in ms. */
const LOGIN_STEP_DEFAULT = 30_000;

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
 * How long each step of `login` waits, in ms: a sixth of the running test's time, so 30 s under the config's
 * 180 s and longer for a spec that gives itself more (`test.slow()`, `test.setTimeout`). The login's steps
 * follow each other, so the test still has time for itself after a slow one.
 */
function loginStepTimeout(): number {
  const timeout = runningTimeout();
  return timeout > 0 ? Math.round(timeout / 6) : LOGIN_STEP_DEFAULT;
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
 * Each step waits `loginStepTimeout()` and a step that does not come fails at once, saying which and how long
 * it waited. runserver or the SaaS restarting (another session saved a `.py` file) refuses the connection for
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
  const wait = loginStepTimeout();
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
  const inHub = () => topbarApps(page).waitFor({ state: 'attached', timeout: wait });
  await withRetry(
    async () => {
      await page.goto(target);
      const where = await Promise.race([
        page.waitForURL((url) => url.origin === SAAS, { timeout: wait }).then(() => 'saas' as const, () => null),
        inHub().then(() => 'hub' as const, () => null),
      ]);
      if (where === null) throw new Error(`login on ${origin}: neither the SaaS nor the hub's shell showed up within ${wait} ms`);
      if (where === 'saas') {
        const form = page.getByTestId('login-form');
        const step = await Promise.race([
          form.waitFor({ state: 'visible', timeout: wait }).then(() => 'form' as const, () => null),
          page.waitForURL((url) => url.origin === origin, { timeout: wait }).then(() => 'back' as const, () => null),
        ]);
        if (step === null) {
          throw new Error(`login on ${origin}: the SaaS showed neither its sign-in form nor the hub within ${wait} ms`);
        }
        if (step === 'form') {
          await signInWithCode(page, origin, target, credentials, wait);
          signedIn = true;
        }
        // Back from the SaaS: the hub's callback sends to `next`. In the hub already, the shell is up and the
        // address final (checked below): waiting for `next` there waited for an address that might never come.
        await page.waitForURL(target, { timeout: wait });
      }
    },
    {
      onRetry: (error) =>
        console.warn(`login on ${origin}: ${String(error).split('\n')[0]}; trying once more in 1 s`),
    },
  );
  await inHub();
  if (signedIn) saasSessions.set(account, await context.cookies(SAAS));
  const opened = await hubSession();
  if (opened !== undefined && opened !== before && (signedIn || ownSaas)) {
    hubSessions.set(hubSessionKey(account, origin), await hubSessionOf(context, origin));
  }
  // Only now is the address final: the SPA mounts its shell once its router has settled, redirects included
  // (`router.isReady()`, frontend/main.ts). Back from the SaaS, the wait above saw `next` as its document arrived.
  const landed = page.url();
  if (new URL(landed).href !== new URL(target).href) {
    throw new Error(`login on ${origin}: landed on ${landed}, not on ${target}: the SPA's router took \`next\` elsewhere`);
  }
}

/**
 * The SaaS's sign-in form (`/launch`) and then, when the SaaS asks for it, the code it mailed
 * (`/verify-email`); done once the browser is on its way back to the hub. A step that does not come within
 * `wait` ms fails with the step's name, the wait and what the page said; a refused connection keeps its own
 * error, so that `login` tries again. Still on `/verify-email` after the code: rejected when the page says so,
 * else a SaaS that has not answered the code yet.
 */
async function signInWithCode(
  page: Page,
  origin: string,
  target: string,
  credentials: Credentials,
  wait: number,
): Promise<void> {
  const form = page.getByTestId('login-form');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  // Taken before the submit: the mail is written while the SaaS answers it.
  const since = Date.now() - MAIL_CLOCK_SLACK;
  await form.getByTestId('login-submit').click();

  const codeForm = page.getByTestId('verify-email-form');
  const backHome = (url: URL) => url.origin === origin || url.pathname.startsWith('/hub-login');
  const step = await Promise.race([
    codeForm.waitFor({ state: 'visible', timeout: wait }).then(() => 'code' as const, () => null),
    page.waitForURL(backHome, { timeout: wait }).then(() => 'back' as const, () => null),
  ]);
  if (step === null) {
    throw new Error(
      `login on ${origin}: sign-in form sent, but neither /verify-email nor the hub came within ${wait} ms${await saidBy(page)}`,
    );
  }
  if (step === 'back') return;

  const code = await readMailCode({ dir: MAIL_DIR, to: credentials.email, since, timeout: wait }).catch((error: unknown) => {
    throw new Error(`login on ${origin}: mail not found: ${error instanceof Error ? error.message : String(error)}`);
  });
  // `CodeField` is one input today; six one-digit inputs would take a digit each.
  const inputs = codeForm.locator('input:not([type=hidden])');
  const count = await inputs.count();
  if (count >= code.length) {
    for (const [i, digit] of [...code].entries()) await inputs.nth(i).fill(digit);
  } else {
    await inputs.first().fill(code);
  }
  await codeForm.getByTestId('verify-email-submit').click();
  try {
    await page.waitForURL(target, { timeout: wait });
  } catch (error) {
    if (isConnectionRefused(error)) throw error;
    const said = await saidBy(page);
    const where =
      new URL(page.url()).pathname !== '/verify-email'
        ? `next not reached within ${wait} ms`
        : said
          ? 'code rejected'
          : `the SaaS did not answer the code within ${wait} ms`;
    throw new Error(`login on ${origin}: ${where} (code ${code} for ${credentials.email}, at ${page.url()})${said}`);
  }
}

/** The alert the page shows, if any, as `: «…»` for an error message. */
async function saidBy(page: Page): Promise<string> {
  // Only decorates an error already being thrown: a page that is gone or navigating adds nothing.
  const alerts = await page
    .locator('[role=alert]:visible')
    .allInnerTexts()
    .catch(() => []);
  const text = alerts.map((alert) => alert.trim()).filter(Boolean).join(' / ');
  return text ? `: «${text}»` : '';
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

/** The demo's API with the context's session (setup and server-side evidence, never the check). */
export async function api<T>(
  context: BrowserContext,
  origin: string,
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<{ status: number; data: T }> {
  // The context also holds the SaaS's cookies (host `localhost`), and Playwright hands them to
  // `a.localhost` too: the token is the hub host's own.
  const host = new URL(origin).hostname;
  const cookies = await context.cookies(origin);
  const csrf = cookies.find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const url = `${origin}/api${path}`;
  const headers = { 'X-CSRFToken': csrf, Accept: 'application/json' };
  const res =
    method === 'GET'
      ? await context.request.get(url, { headers })
      : await context.request.post(url, { headers, data: body ?? {} });
  const text = await res.text();
  return { status: res.status(), data: (text ? JSON.parse(text) : null) as T };
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
 * on), until the server says the business is empty (phase 1: `a` and `b` share these rows).
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

/**
 * Turns on `apps` in the business at `origin`, as the person of `context` who runs it, through Apps' own command
 * (`POST /api/apps/enable`, `base.app.enable`): a business is born with every app off (PLAN-HUB round 2026-10-27).
 * One already on changes nothing.
 */
export async function turnOn(context: BrowserContext, origin: string, ...apps: string[]): Promise<void> {
  for (const app of apps) {
    const answer = await api(context, origin, 'POST', '/apps/enable', { app });
    expect(answer.status, `turn on ${app}: ${JSON.stringify(answer.data)}`).toBe(200);
  }
}

/** Deletes every demo item (phase 1: `a` and `b` share them), through the API. */
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
 * The ⠿ «My apps» button of the hub's topbar (its sidebar, PLAN-MIGRATIONS §16): there once the
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

export function psql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${STACK.database} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
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
  const body = JSON.stringify({ ...registration, country });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', INTERNAL_SECRET).update(`${timestamp}.${body}`).digest('hex');
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/hubs/${registration.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(psql(`select country from base_hub where slug = '${registration.slug}'`)).toBe(country);
}

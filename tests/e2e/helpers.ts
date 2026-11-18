// The helpers the browser specs share: the hub's API, the real login, the page on view, the one wait for «nothing
// moves», the captures and the SQL on the stack's databases.
//
// The local hubs `a` and `b` answer only once they are rows of the registry (`base.Hub`): without them every
// host is a 404. `manage.py seed_local_hubs` (DEBUG only, idempotent) adds them;
// `database.ts` runs it on an e2e database and `global-setup.ts` checks it (`seed_local_hubs --check`) before
// the first spec. The shared `hub` database needs it once, by hand.
import { execSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Browser, type BrowserContext, type Cookie, expect, type Locator, type Page } from '@playwright/test';

import { movingInPage, repeatedTop } from './detectors';
import { hubDatabases, plan } from './hub-databases';
import { withRetry } from './retry';
import { alongTheTrip, goneOrJumped, loginTimeout, SAAS, sameAddress, shellOrSaas, signInWithCode, watchTrip } from './saas-login';
import { REPO_DIR, STACK } from './stack';

// The hub's API for the e2e helpers (setup and server-side evidence, never the check), and a hub busy for a moment.
// The stack's businesses run with Free's limits (one transaction at once, `base.tenancy.limits`): with the machine
// loaded, the page a spec just opened can hold that place past the server's wait, and the hub answers 503
// `base.hub_busy` («Too many requests. Try again in a moment.»). That answer ran nothing (`HubBusy` is refused before
// any statement: `OperationError.retry_after`), so the same request goes again after the server's `Retry-After`, a few
// times; a hub that stays busy fails, saying so (hub#795). Any other answer is the caller's to check.

/** Tries in all, the first included: about 15 s at most (each try waits up to 2 s for a place, then the pause). */
const HUB_BUSY_TRIES = 6;
/** The pause before another try: the server's `Retry-After` (`RETRY_AFTER_SECONDS`, `base.tenancy.limits`). */
const HUB_BUSY_PAUSE_MS = 1000;

/** The hub still had no place for the request after every try. */
class HubStillBusy extends Error {
  override name = 'HubStillBusy';
}

/** The hub's 503 `base.hub_busy`: its error envelope, never another 503 (a business being moved, a database down). */
function isHubBusy(status: number, data: unknown): boolean {
  return status === 503 && (data as { error?: { code?: unknown } } | null)?.error?.code === 'base.hub_busy';
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
  const route = `${method} /api${path}`;
  return withRetry(
    async (attempt) => {
      const res =
        method === 'GET'
          ? await context.request.get(url, { headers })
          : await context.request.post(url, { headers, data: body ?? {} });
      const text = await res.text();
      const answer = { status: res.status(), data: (text ? JSON.parse(text) : null) as T };
      if (isHubBusy(answer.status, answer.data)) {
        throw new HubStillBusy(`${route}: the hub was still busy after ${attempt} tries, ${HUB_BUSY_PAUSE_MS} ms apart: ${answer.status} ${text}`);
      }
      return answer;
    },
    {
      attempts: HUB_BUSY_TRIES,
      isRetryable: (error) => error instanceof HubStillBusy,
      delayMs: HUB_BUSY_PAUSE_MS,
      onRetry: (_error, attempt) =>
        console.warn(`${route}: the hub is busy (503 base.hub_busy); trying again in ${HUB_BUSY_PAUSE_MS} ms (${attempt + 1} of ${HUB_BUSY_TRIES})`),
    },
  );
}

export const A = STACK.hub('a');

/** The three sizes the e2e looks at a screen in: a phone, a tablet and a desk. */
export const THREE_SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;
export const B = STACK.hub('b');

const HERE = dirname(fileURLToPath(import.meta.url));
export const ARTIFACTS = join(HERE, '.artifacts');
const METRICS = join(ARTIFACTS, 'metrics');

/** How long `untilStill` waits for the page to stop moving: Ionic's overlays enter in well under a second. */
const STILL_TIMEOUT_MS = 10_000;

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

/** A SaaS account: what its sign-in page asks for. */
export interface Credentials {
  email: string;
  password: string;
}
/** The demo customer account in the SaaS (`saas … demo_seed`): owner of hubs `a` and `b`. */
export const OWNER: Credentials = { email: 'owner@example.com', password: 'owner' };
/** The demo employee in the SaaS (`demo_seed`): `hub_employee` of `a` and `b`, views Demo only. */
export const EMPLOYEE: Credentials = { email: 'employee@example.com', password: 'employee' };

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
 * `alongTheTrip`); the SaaS sent the page to its error page, refusing the sign-in or the jump (`alongTheTrip`); the SaaS
 * turned down or failed the sign-in or the code, or one of them got no answer at all; the SaaS asked for the code
 * without a mail with it (`signInWithCode`).
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

/** What the page on screen marks with this `data-testid`. */
export const testid = (page: Page, id: string): Locator => shown(page).locator(`[data-testid="${id}"]`);

/** `id`'s row in the Apps screen. */
export const appRow = (page: Page, id: string): Locator => shown(page).locator(`[data-testid="apps-row"][data-id="${id}"]`);

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
const OVERLAYS = 'ion-modal, ion-popover, ion-alert, ion-action-sheet, ion-loading, ion-picker-legacy';

/**
 * The page shown by `IonRouterOutlet` (hidden pages stay in the DOM), never a dialog presented over it:
 * Ionic moves a presented modal to `ion-app`, after the pages, so the last visible `.ion-page` would be the
 * dialog's. A dialog is found with `page.locator('ion-modal[data-testid=…]')`, not here.
 */
export const shown = (page: Page): Locator =>
  page.locator(`.ion-page:not(.ion-page-hidden):not(:is(${OVERLAYS}) *)`).last();

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

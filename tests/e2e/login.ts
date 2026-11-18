// The real login of a hub through the SaaS, with the sessions it keeps for each worker, and the pages the specs open
// signed in with it.
import { type Browser, type BrowserContext, type Cookie, expect, type Page } from '@playwright/test';

import { alongTheTrip, loginTimeout, shellOrSaas, signInWithCode, watchTrip } from './login-trip';
import { withRetry } from './retry';
import { type Credentials, OWNER, SAAS } from './saas';
import { A } from './stack';

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

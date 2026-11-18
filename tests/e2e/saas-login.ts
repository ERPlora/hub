// The stack's SaaS, where every login goes: its address, where its sign-in posts, the folder of the mails with its
// codes, and the steps of a login's trip through it and back to the hub's shell, which fail at once on what says a
// step is not coming; and what the page says while a spec runs.
import { type Frame, type Locator, type Page, type Request as PageRequest, type Response as PageResponse, test } from '@playwright/test';

import type { Credentials } from './helpers';
import { mailDirFrom, readMailCode } from './mail';
import { REPO_DIR, STACK } from './stack';

/** The SaaS (`erplora.com` in production): the only login page a hub has. */
export const SAAS = STACK.saas;

/**
 * Whether `page` is on the SaaS (its login): what its console says there is the SaaS's, judged by the SaaS's own
 * suite. Its headless API answers 401 while nobody is signed in (allauth's protocol), and Chrome logs each one.
 */
export const onSaas = (page: Page): boolean => new URL(page.url()).origin === SAAS;

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
/** The SaaS's page that says why it refused a sign-in or a jump to a hub (`?code=not_a_member`, `too_many`…): nothing goes on from there by itself. */
const SAAS_REFUSED = '/login/error';

/** The running test's (or hook's) time limit, in ms; 0 outside a test or hook, as with no limit. */
export function runningTimeout(): number {
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
export function loginTimeout(): number {
  return runningTimeout() || LOGIN_DEFAULT;
}

/** Whether two addresses are the same once written the same way (`http://a.localhost:8000` and `…:8000/`). */
export const sameAddress = (one: string, other: string): boolean => new URL(one).href === new URL(other).href;

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
export async function goneOrJumped(page: Page, target: string, origin: string): Promise<boolean> {
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
export function watchTrip(page: Page, origin: string): TripWatch {
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
export async function shellOrSaas(
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
 * `trip` saw, `refused`, the page at an address that is neither this hub nor the SaaS (Chrome's error page among
 * them), or the page on the SaaS's own error page (`SAAS_REFUSED`), where it refused the sign-in or the jump.
 */
export async function alongTheTrip<T>(page: Page, origin: string, trip: TripWatch, step: Promise<T>, options: Along): Promise<T>;
export async function alongTheTrip<T>(
  page: Page,
  origin: string,
  trip: TripWatch,
  step: Promise<T>,
  options: Along & { back: (url: URL) => boolean },
): Promise<T | 'back'>;
export async function alongTheTrip<T>(
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
      } else if (siteOf(url, origin) === 'saas' && new URL(url).pathname === SAAS_REFUSED) {
        reject(new Error(`login on ${origin}: the SaaS stopped the login on its error page ${url}`));
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
export async function signInWithCode(
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

/** What opens «My apps» on the hub's topbar: its ⠿ button from a tablet, the shell's «⋮» on a phone. */
export const MY_APPS_DOOR = '[data-testid=topbar-apps], [data-testid=topbar-more]';

/** The way to «My apps»: there once the authenticated shell is painted (every page of the stack has its own). */
export const topbarApps = (page: Page): Locator => page.locator(MY_APPS_DOOR).first();


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

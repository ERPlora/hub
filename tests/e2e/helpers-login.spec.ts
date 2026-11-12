// flow: ninguno — FIX base (ayudante `login` de los e2e del Hub; visto en hub#107 y hub#1370)
// `login` on a loaded machine (hub#107: «next not reached», then «code rejected»). What fell was the SaaS's
// answer to the mailed code (`POST …/auth/code/confirm`), 30 and 37 s on the server: allauth's user sessions walk
// every open session of the account at each sign-in, and every login of the e2e signed in again and left one
// more (1680 for owner@example.com in the shared `saas` database). So an account signs in to the SaaS once per
// worker and later logins reuse that SaaS session, as a person signed in at erplora.com: the SaaS skips its
// form and its code and only hands the hub its one-time code. A SaaS session that ended (a spec signed out
// there) falls back to the real sign-in, whose session is reused next.
// A SaaS slow at a step, however slow, is waited for (hub#1370: each step had a sixth of the test's time and fell
// with nothing wrong): its answer here comes later than that on purpose, the test itself never waits. «code
// rejected» is only what the SaaS answers, and a code that gets no answer says so, whatever the page shows.
// Every login here is about the trip through the SaaS, so it asks for the jump (`fresh: true`): without it, `login`
// would reuse the hub's session it keeps and never reach the SaaS (FIX-HUB-E2E-HUB-LOGIN-RATELIMIT-429).
import { type Browser, type BrowserContext, expect, type Route, test } from '@playwright/test';

import { A, hostPage, listReady, login, OWNER, SAAS, shot, topbarApps } from './helpers';

/** What `login` is given here: the trip through the SaaS, even with a session of the hub kept. */
const JUMP = { fresh: true };

const SIGN_IN = `${SAAS}/_allauth/browser/v1/auth/login`;
const CODE = `${SAAS}/_allauth/browser/v1/auth/code/confirm`;

const VIEWPORTS = [
  { label: '1440', width: 1440, height: 900 },
  { label: '834', width: 834, height: 1112 },
  { label: '390', width: 390, height: 844 },
];

/** The password sign-ins the context posts to the SaaS from now on. */
function signInsOf(context: BrowserContext): string[] {
  const posts: string[] = [];
  context.on('request', (request) => {
    if (request.method() === 'POST' && request.url() === SIGN_IN) posts.push(request.url());
  });
  return posts;
}

/** A SaaS that never answers the code: each one sent is held until `release()` aborts it. */
async function holdCodes(context: BrowserContext): Promise<{ held: Route[]; release: () => Promise<void> }> {
  const held: Route[] = [];
  await context.route(CODE, (route) => {
    held.push(route);
  });
  const release = async () => {
    await Promise.all(held.map((route) => route.abort().catch(() => undefined)));
  };
  return { held, release };
}

/**
 * A SaaS slower than a step of the login used to wait for it (a sixth of the test's time): what the page posts to `url`
 * reaches the SaaS that much later and a little more. `late` is that delay; `took`, how long each post was held.
 */
async function answerLate(context: BrowserContext, url: string): Promise<{ late: number; took: number[] }> {
  const late = test.info().timeout / 6 + 5_000;
  const took: number[] = [];
  await context.route(url, async (route) => {
    const since = Date.now();
    await new Promise((resolve) => setTimeout(resolve, late));
    took.push(Date.now() - since);
    // The context may be gone by then, its page with it.
    await route.continue().catch(() => undefined);
  });
  return { late, took };
}

/** «Sign out» at erplora.com in that context (allauth.headless): its SaaS session ends. */
async function signOutOfSaas(context: BrowserContext): Promise<void> {
  const csrf = (await context.cookies(SAAS)).find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
  const res = await context.request.delete(`${SAAS}/_allauth/browser/v1/auth/session`, { headers: { 'X-CSRFToken': csrf } });
  expect(res.status(), 'signed out of the SaaS (allauth answers 401: nobody signed in)').toBe(401);
}

/** A login of the owner whose SaaS session then ends: the next login signs in with the SaaS's form and its code. */
async function endSaasSession(browser: Browser): Promise<void> {
  const first = await hostPage(browser, A);
  await signOutOfSaas(first.context);
  await first.context.close();
}

test('a second login of the account reuses its SaaS session: no sign-in and no code to wait for', async ({ browser }) => {
  const first = await hostPage(browser, A);
  await first.context.close();

  const context = await browser.newContext({ baseURL: A });
  const signIns = signInsOf(context);
  const codes = await holdCodes(context);
  try {
    const page = await context.newPage();
    await login(page, A, '/demo/items', OWNER, JUMP);
    await expect(topbarApps(page)).toBeAttached();
    expect(signIns, 'password sign-ins at the SaaS').toEqual([]);
    expect(codes.held, 'codes sent to the SaaS').toEqual([]);
    for (const { label, width, height } of VIEWPORTS) {
      await page.setViewportSize({ width, height });
      await listReady(page);
      await page.screenshot({ path: shot(`FIX-HUB-E2E-LOGIN-FLAKY-UNDER-LOAD-${label}`) });
    }
  } finally {
    await codes.release();
    await context.close();
  }
});

test('its SaaS session ended, the next login signs in for real and the one after reuses the new session', async ({ browser }) => {
  await endSaasSession(browser);

  const again = await browser.newContext({ baseURL: A });
  const signInsAgain = signInsOf(again);
  await login(await again.newPage(), A, '/demo/items', OWNER, JUMP);
  expect(signInsAgain, 'the ended session asks for the account again').toHaveLength(1);
  await again.close();

  const after = await browser.newContext({ baseURL: A });
  const signInsAfter = signInsOf(after);
  await login(await after.newPage(), A, '/demo/items', OWNER, JUMP);
  expect(signInsAfter, 'the new session is reused').toEqual([]);
  await after.close();
});

test('a SaaS slow to answer the code: the login waits for its answer, longer than a step had, and signs in', async ({ browser }) => {
  test.setTimeout(90_000);
  await endSaasSession(browser);

  const context = await browser.newContext({ baseURL: A });
  const codes = await answerLate(context, CODE);
  try {
    const page = await context.newPage();
    await login(page, A, '/demo/items', OWNER, JUMP);
    await expect(topbarApps(page)).toBeAttached();
    expect(codes.took, 'the code reached the SaaS once, later than a step had').toEqual([expect.any(Number)]);
    expect(codes.took[0]).toBeGreaterThanOrEqual(codes.late);
  } finally {
    await context.close();
  }
});

test('a SaaS slow to answer the sign-in: the login waits for its code form and signs in', async ({ browser }) => {
  test.setTimeout(90_000);
  await endSaasSession(browser);

  const context = await browser.newContext({ baseURL: A });
  const signIns = await answerLate(context, SIGN_IN);
  try {
    const page = await context.newPage();
    await login(page, A, '/demo/items', OWNER, JUMP);
    await expect(topbarApps(page)).toBeAttached();
    expect(signIns.took, 'the sign-in reached the SaaS once, later than a step had').toEqual([expect.any(Number)]);
    expect(signIns.took[0]).toBeGreaterThanOrEqual(signIns.late);
  } finally {
    await context.close();
  }
});

test('a code that gets no answer (its connection reset): the login says the SaaS did not answer it, not «code rejected»', async ({
  browser,
}) => {
  test.setTimeout(90_000);
  await endSaasSession(browser);

  const context = await browser.newContext({ baseURL: A });
  // Every code sent is dropped on its way: the SaaS's page then says it could not sign in, which the SaaS never said.
  const dropped: string[] = [];
  await context.route(CODE, async (route) => {
    dropped.push(route.request().url());
    await route.abort('connectionreset');
  });
  try {
    const failure = await login(await context.newPage(), A, '/demo/items', OWNER, JUMP).then(
      () => 'signed in',
      (error: unknown) => String(error),
    );
    expect(dropped.length, 'codes sent').toBeGreaterThanOrEqual(1);
    expect(failure).toMatch(/: the SaaS did not answer the code \(net::ERR_CONNECTION_RESET\) \(code \d{6} for owner@example\.com, at .+\)/);
    expect(failure).not.toContain('code rejected');
  } finally {
    await context.close();
  }
});

test('a code the SaaS turns down: the login says «code rejected», what the SaaS answered and what it said', async ({ browser }) => {
  test.setTimeout(90_000);
  await endSaasSession(browser);

  const context = await browser.newContext({ baseURL: A });
  // The mailed code goes out as another one: the SaaS itself refuses it (400) and says why under the field.
  const answers: number[] = [];
  await context.route(CODE, async (route) => {
    const sent = JSON.parse(route.request().postData() ?? '{}') as { code?: string };
    const response = await route.fetch({ postData: JSON.stringify({ ...sent, code: sent.code === '000000' ? '111111' : '000000' }) });
    answers.push(response.status());
    await route.fulfill({ response });
  });
  try {
    const failure = await login(await context.newPage(), A, '/demo/items', OWNER, JUMP).then(
      () => 'signed in',
      (error: unknown) => String(error),
    );
    expect(answers, 'the SaaS answered the code').toEqual([400]);
    expect(failure).toMatch(/: code rejected, the SaaS answered 400 \(code \d{6} for owner@example\.com, at .+\): «.+»$/);
    expect(failure).not.toContain('did not answer');
  } finally {
    await context.close();
  }
});

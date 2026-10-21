// flow: ninguno — FIX base (ayudante `login` de los e2e del Hub; visto en hub#107)
// `login` on a loaded machine (hub#107: «next not reached», then «code rejected»). What fell was the SaaS's
// answer to the mailed code (`POST …/auth/code/confirm`), 30 and 37 s on the server: allauth's user sessions walk
// every open session of the account at each sign-in, and every login of the e2e signed in again and left one
// more (1680 for owner@example.com in the shared `saas` database). So an account signs in to the SaaS once per
// worker and later logins reuse that SaaS session, as a person signed in at erplora.com: the SaaS skips its
// form and its code and only hands the hub its one-time code. A SaaS session that ended (a spec signed out
// there) falls back to the real sign-in, whose session is reused next. And a SaaS slow to answer the code is
// said as such, with the time waited: «code rejected» is only what the SaaS itself says.
import { type BrowserContext, expect, type Route, test } from '@playwright/test';

import { A, hostPage, listReady, login, SAAS, shot, topbarApps } from './helpers';

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

/** «Sign out» at erplora.com in that context (allauth.headless): its SaaS session ends. */
async function signOutOfSaas(context: BrowserContext): Promise<void> {
  const csrf = (await context.cookies(SAAS)).find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
  const res = await context.request.delete(`${SAAS}/_allauth/browser/v1/auth/session`, { headers: { 'X-CSRFToken': csrf } });
  expect(res.status(), 'signed out of the SaaS (allauth answers 401: nobody signed in)').toBe(401);
}

test('a second login of the account reuses its SaaS session: no sign-in and no code to wait for', async ({ browser }) => {
  const first = await hostPage(browser, A);
  await first.context.close();

  const context = await browser.newContext({ baseURL: A });
  const signIns = signInsOf(context);
  const codes = await holdCodes(context);
  try {
    const page = await context.newPage();
    await login(page, A);
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
  const first = await hostPage(browser, A);
  await signOutOfSaas(first.context);
  await first.context.close();

  const again = await browser.newContext({ baseURL: A });
  const signInsAgain = signInsOf(again);
  await login(await again.newPage(), A);
  expect(signInsAgain, 'the ended session asks for the account again').toHaveLength(1);
  await again.close();

  const after = await browser.newContext({ baseURL: A });
  const signInsAfter = signInsOf(after);
  await login(await after.newPage(), A);
  expect(signInsAfter, 'the new session is reused').toEqual([]);
  await after.close();
});

test('a SaaS slow to answer the code: the login says it waited for the answer and how long, not «code rejected»', async ({
  browser,
}) => {
  // The login's waits are a sixth of the test's time: 15 s here, 30 s under the config's 180 s.
  test.setTimeout(90_000);
  const first = await hostPage(browser, A);
  // Its SaaS session ended, the next login signs in with the form and the code.
  await signOutOfSaas(first.context);
  await first.context.close();

  const context = await browser.newContext({ baseURL: A });
  const codes = await holdCodes(context);
  try {
    const failure = await login(await context.newPage(), A).then(
      () => 'signed in',
      (error: unknown) => String(error),
    );
    expect(codes.held, 'the code was sent').toHaveLength(1);
    expect(failure).toContain('the SaaS did not answer the code within 15000 ms');
    expect(failure).not.toContain('code rejected');
  } finally {
    await codes.release();
    await context.close();
  }
});

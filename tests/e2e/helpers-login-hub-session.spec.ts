// flow: ninguno — FIX base (ayudante `login` de los e2e del Hub; visto en hub#179)
// `login` and the SaaS's brake on jumps (FIX-HUB-E2E-HUB-LOGIN-RATELIMIT-429). Every jump to a hub is counted by the
// SaaS, 20 per account every 5 minutes (`HUB_LOGIN_RATELIMIT`, ACCOUNTS-F28), and a spec of more than 20 tests, each
// in a fresh context, fell at the 21st with «429 · Too many attempts» (staff-flows.spec.ts, STAFF-F24). So `login`
// keeps the hub's session of each account and hub, as a person who comes back to their business: a fresh context
// starts with it and lands on `next` with no jump. A session that ended (signed out of the hub) sends to the SaaS
// as before, and the new one is kept; `fresh: true` asks for the jump on purpose.
import { type Browser, type BrowserContext, expect, test } from '@playwright/test';

import { A, api, B, EMPLOYEE, listReady, login, type Credentials, OWNER, shot } from './helpers';

/** One more than the SaaS lets an account jump in 5 minutes (`HUB_LOGIN_RATELIMIT`, 20/5m by default). */
const ENTRIES = 21;

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** The one-time codes the context hands to a hub from now on (`POST <origin>/auth/callback`): its jumps. */
function jumpsOf(context: BrowserContext): string[] {
  const jumps: string[] = [];
  context.on('request', (request) => {
    const url = new URL(request.url());
    if (request.method() === 'POST' && url.pathname === '/auth/callback') jumps.push(url.origin);
  });
  return jumps;
}

/** A fresh context signed in on `origin` as `credentials`: who the hub says it is and the jumps it took. */
async function entry(
  browser: Browser,
  origin: string,
  credentials: Credentials = OWNER,
  options: { fresh?: boolean } = {},
): Promise<{ context: BrowserContext; user: string; jumps: string[] }> {
  const context = await browser.newContext({ baseURL: origin });
  const jumps = jumpsOf(context);
  const page = await context.newPage();
  await login(page, origin, '/demo/items', credentials, options);
  const me = await api<{ user: { id: string } | null }>(context, origin, 'GET', '/me');
  expect(me.status, `GET /api/me on ${origin}`).toBe(200);
  return { context, user: me.data.user?.id ?? '', jumps };
}

/** «Sign out» of the hub in that context (`POST /auth/logout`): the hub's session ends, the SaaS's stays. */
async function signOutOfHub(context: BrowserContext, origin: string): Promise<void> {
  const host = new URL(origin).hostname;
  const csrf = (await context.cookies(origin)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const res = await context.request.post(`${origin}/auth/logout`, { headers: { 'X-CSRFToken': csrf }, maxRedirects: 0 });
  expect(res.status(), 'signed out of the hub (a redirect to the SaaS)').toBe(302);
}

test(`${ENTRIES} entries in a row of one account, each in a fresh context: one jump at most, never the SaaS's 429`, async ({
  browser,
}) => {
  let jumps = 0;
  for (let n = 1; n <= ENTRIES; n++) {
    const context = await browser.newContext({ baseURL: A });
    const seen = jumpsOf(context);
    try {
      const page = await context.newPage();
      const failed = await login(page, A).then(
        () => null,
        (error: unknown) => `${String(error).split('\n')[0]} (at ${page.url()})`,
      );
      expect(failed, `entry ${n} of ${ENTRIES}`).toBeNull();
      jumps += seen.length;
      if (n === ENTRIES) {
        for (const { label, width, height } of VIEWPORTS) {
          await page.setViewportSize({ width, height });
          await listReady(page);
          await page.screenshot({ path: shot(`FIX-HUB-E2E-HUB-LOGIN-RATELIMIT-429-${label}`) });
        }
      }
    } finally {
      await context.close();
    }
  }
  expect(jumps, `jumps to the hub in ${ENTRIES} entries`).toBeLessThanOrEqual(1);
});

test('the kept session is the account’s and the hub’s: the employee enters as itself, hub b as b, and none of them jumps again', async ({
  browser,
}) => {
  const first = [await entry(browser, A), await entry(browser, A, EMPLOYEE), await entry(browser, B)];
  for (const { context } of first) await context.close();
  const [owner, employee] = first;
  expect(owner.user, 'the owner and the employee are two users of the hub').not.toBe(employee.user);

  const again = [await entry(browser, A), await entry(browser, A, EMPLOYEE), await entry(browser, B)];
  try {
    expect(again.map((e) => e.user), 'each one enters as itself').toEqual(first.map((e) => e.user));
    expect(again.flatMap((e) => e.jumps), 'jumps of the second round').toEqual([]);
  } finally {
    for (const { context } of again) await context.close();
  }
});

test('a kept session that ended (signed out of the hub): the next login jumps for real and the one after reuses the new session', async ({
  browser,
}) => {
  const before = await entry(browser, A);
  await signOutOfHub(before.context, A);
  await before.context.close();

  const after = await entry(browser, A);
  await after.context.close();
  expect(after.jumps, 'the ended session asks the SaaS again').toEqual([A]);
  expect(after.user, 'the same account').toBe(before.user);

  const next = await entry(browser, A);
  await next.context.close();
  expect(next.jumps, 'the new session is reused').toEqual([]);
});

test('a context signed in at the SaaS as another account: the session its jump opens is not kept for the account asked', async ({
  browser,
}) => {
  // A context with the employee's SaaS session (`login` gives it the one it keeps).
  const employee = await entry(browser, A, EMPLOYEE);
  try {
    // The same context jumps to hub b asked for the owner: the SaaS still has the employee signed in, and the jump
    // opens theirs.
    const page = await employee.context.newPage();
    await login(page, B, '/demo/items', OWNER, { fresh: true });
    const there = await api<{ user: { id: string } | null }>(employee.context, B, 'GET', '/me');
    expect(there.data.user?.id, 'what the SaaS signed in').toBe(employee.user);
  } finally {
    await employee.context.close();
  }

  const owner = await entry(browser, B);
  await owner.context.close();
  expect(owner.user, 'the owner enters hub b as the owner').not.toBe(employee.user);
});

test('`fresh: true` jumps through the SaaS even with a kept session, and keeps the new one', async ({ browser }) => {
  const kept = await entry(browser, A);
  await kept.context.close();

  const fresh = await entry(browser, A, OWNER, { fresh: true });
  await fresh.context.close();
  expect(fresh.jumps, 'a real jump').toEqual([A]);

  const next = await entry(browser, A);
  await next.context.close();
  expect(next.jumps, 'the session of that jump is reused').toEqual([]);
  expect(next.user).toBe(kept.user);
});

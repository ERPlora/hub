// The demo hubs end to end (plan docs/plans/2026-10-17-demo-hubs-fase-1.md §3 «e2e»; README «Demo»): the SaaS's
// /demo/ → «Try the demo» → an empty `demo-<8 hex>` hub with the shell and the session «Demo», no account, born with
// every app off but Taxes like any business (PLAN-HUB rounds 2026-10-27 and 2026-11-07); the Demo app turned on and something real made in it; `manage.py demo_expire` ends it before its hour (the e2e's clock, as support's) → the host
// answers 410 «This demo has ended», whose link takes the visitor to the SaaS's /demo/?state=expired, which
// forgets the demo the session still held as live. Zero CSP violations on the hub's pages.
//
// It needs the SaaS with the demo door and its HUB_INTERNAL_URL on this stack's Hub (README of this folder,
// «La demo»): the SaaS calls the Hub's /internal/demos itself, so a SaaS pointed at another Hub's port creates
// the demo there and this run never finds it. And its limit of new demos per address raised, as the README's recipe
// starts it (`DEMO_SPAWN_RATELIMIT`, demo-door.ts): every run starts two from 127.0.0.1, and it lets 3 an hour.
import { execFileSync } from 'node:child_process';

import { expect, type Locator, type Page, test } from '@playwright/test';

import { doorOutcome, noDemoBecause } from './demo-door';
import { api, collectProblems, createViaPage, HUB_DIR, listReady, rowNames, SAAS, shot, shown, turnOn, uniqueName } from './helpers';
import { STACK } from './stack';

const DEMO_HOST = new RegExp(`^http://(demo-[0-9a-f]{8})\\.localhost:${STACK.hubPort}/`);
const DOOR = `${SAAS}/demo/`;

interface Me {
  user: { id: string; label: string } | null;
  demo: { expires_at: string } | null;
}

/** The door's state (`data-testid="demo-state-<state>"`, public/demo.py of the SaaS). */
async function doorSays(page: Page, state: string): Promise<void> {
  await expect(page.getByTestId(`demo-state-${state}`)).toBeVisible();
}

/** The door's «Back to my demo»: a link, as the public web draws its buttons (`{% button %}`, saas#246), found by its
 *  role and name, not by the element that draws it (an `ion-button` until then: hub#1040). */
function backToMyDemo(page: Page): Locator {
  return page.getByRole('link', { name: 'Back to my demo', exact: true });
}

/** Where «Back to my demo» goes: the jump into the demo `slug` on this stack's Hub (its `/auth/login`, the SaaS's
 *  `hub_start_url`), never another demo's. */
function jumpInto(slug: string): RegExp {
  return new RegExp(`^http://${slug}\\.localhost:${STACK.hubPort}/auth/login\\?`);
}

/** How long a demo may take to be ready, door to shell: since S3 its sign-up is the clone of its template (every app off,
 *  an app's tables made when it is turned on), measured at 1.4–4.1 s from its request to `ready` with the worker's 5 s
 *  tick (2026-10-31; 13–32 s while every app's tables were made at sign-up). PLAN-DB §6 aims at 5 s: 15 s is the tick
 *  and that aim with room for a loaded machine, and a sign-up that makes tables again fails here. */
const DEMO_READY_MS = 15_000;

/** «Try the demo» on the door, then the jump through the demo's /auth/login and callback: its slug, once its shell
 *  is up. A door that answers with an outcome instead (`?state=throttled`…) fails the run at once saying which, not
 *  as a demo that never got ready (hub#1048). */
async function startDemo(page: Page): Promise<string> {
  await page.getByTestId('demo-start').click();
  await page.waitForURL((url) => DEMO_HOST.test(url.href) || doorOutcome(url.href, DOOR) !== null, { timeout: DEMO_READY_MS });
  const refused = doorOutcome(page.url(), DOOR);
  if (refused) throw new Error(noDemoBecause(refused));
  await shown(page).locator('[data-testid=topbar-apps]').waitFor({ state: 'attached', timeout: DEMO_READY_MS });
  const slug = DEMO_HOST.exec(page.url())?.[1];
  if (!slug) throw new Error(`not on a demo host: ${page.url()}`);
  return slug;
}

/** `manage.py demo_expire <slug>` of this checkout, against this run's database (`DB_NAME`): what it printed. */
function expireNow(slug: string): string {
  return execFileSync('uv', ['run', 'python', 'manage.py', 'demo_expire', slug], {
    cwd: HUB_DIR,
    env: { ...process.env, DEBUG: 'True' },
    encoding: 'utf8',
  }).trim();
}

test('a demo from the SaaS door: empty hub as «Demo», something made, ended now → 410 → the door says it ended', async ({
  page,
  context,
}) => {
  const problems = await collectProblems(page);

  await page.goto(DOOR);
  await doorSays(page, 'idle');
  const slug = await startDemo(page);
  const origin = STACK.hub(slug);

  const me = await api<Me>(context, origin, 'GET', '/me');
  expect(me.status).toBe(200);
  expect(me.data.user?.label).toBe('Demo');
  expect(Date.parse(me.data.demo?.expires_at ?? '')).toBeGreaterThan(Date.now());

  // Born with every app off, as any business: the visitor turns on the app they try.
  const apps = await api<{ apps: { id: string; state: string }[] }>(context, origin, 'GET', '/apps');
  expect(apps.status).toBe(200);
  expect(apps.data.apps.filter((app) => app.state !== 'off')).toEqual([]);
  await turnOn(context, origin, 'demo');

  await page.goto(`${origin}/demo/items`);
  await listReady(page);
  const name = uniqueName('Demo probe');
  await createViaPage(page, name);
  expect(await rowNames(page)).toContain(name);
  await page.screenshot({ path: shot('demo-01-item-made') });

  // Back on the door, the session holds the live demo.
  await page.goto(DOOR);
  await doorSays(page, 'ready');
  await expect(backToMyDemo(page)).toHaveAttribute('href', jumpInto(slug));

  expect(expireNow(slug)).toBe(`${slug}: purged`);

  const gone = await page.goto(`${origin}/demo/items`);
  expect(gone?.status()).toBe(410);
  await expect(page.getByRole('heading', { name: 'This demo has ended' })).toBeVisible();
  const back = page.getByRole('link', { name: 'Create another demo' });
  await expect(back).toHaveAttribute('href', `${DOOR}?state=expired`);
  await page.screenshot({ path: shot('demo-02-gone-410') });
  const envelope = await api<{ error: { code: string } }>(context, origin, 'GET', '/me');
  expect([envelope.status, envelope.data.error.code]).toEqual([410, 'base.hub_gone']);

  // The 410's link: the door forgets the demo (its expires_at has not passed) and says once that it ended.
  await back.click();
  await page.waitForURL(`${DOOR}?state=expired`);
  await doorSays(page, 'expired');
  await expect(page.getByTestId('demo-start')).toBeVisible();
  // Nothing on it offers the ended demo back, whatever draws the offer: a link, or a button that is not one.
  await expect(page.getByText('Back to my demo', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: shot('demo-03-door-expired') });
  await page.goto(DOOR);
  await doorSays(page, 'idle');

  // Another try is another demo.
  const another = await startDemo(page);
  expect(another).not.toBe(slug);
  expect(expireNow(another)).toBe(`${another}: purged`);

  const found = await problems();
  expect(found.csp).toEqual([]);
  expect(found.page).toEqual([]);
  // The one console error a hub page may log is the browser's own line about the 410 asked for on purpose.
  expect(found.console.filter((line) => !/status of 410/.test(line))).toEqual([]);
});

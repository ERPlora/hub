// The demo hubs end to end (plan docs/plans/2026-10-17-demo-hubs-fase-1.md §3 «e2e»; README «Demo»): the SaaS's
// /demo/ → «Try the demo» → an empty `demo-<8 hex>` hub with the shell and the session «Demo», no account; something
// real made in it; `manage.py demo_expire` ends it before its hour (the e2e's clock, as support's) → the host
// answers 410 «This demo has ended», whose link takes the visitor to the SaaS's /demo/?state=expired, which
// forgets the demo the session still held as live. Zero CSP violations on the hub's pages.
//
// It needs the SaaS with the demo door and its HUB_INTERNAL_URL on this stack's Hub (README of this folder,
// «La demo»): the SaaS calls the Hub's /internal/demos itself, so a SaaS pointed at another Hub's port creates
// the demo there and this run never finds it.
import { execFileSync } from 'node:child_process';

import { expect, type Page, test } from '@playwright/test';

import { api, collectProblems, createViaPage, HUB_DIR, listReady, rowNames, SAAS, shot, shown, uniqueName } from './helpers';
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

/** «Try the demo» on the door, then the jump through the demo's /auth/login and callback: its slug, once its shell
 *  is up. */
async function startDemo(page: Page): Promise<string> {
  await page.getByTestId('demo-start').click();
  await page.waitForURL(DEMO_HOST, { timeout: 30_000 });
  await shown(page).locator('[data-testid=topbar-apps]').waitFor({ state: 'attached', timeout: 30_000 });
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

  await page.goto(`${origin}/demo/items`);
  await listReady(page);
  const name = uniqueName('Demo probe');
  await createViaPage(page, name);
  expect(await rowNames(page)).toContain(name);
  await page.screenshot({ path: shot('demo-01-item-made') });

  // Back on the door, the session holds the live demo.
  await page.goto(DOOR);
  await doorSays(page, 'ready');
  await expect(page.locator('ion-button', { hasText: 'Back to my demo' })).toHaveAttribute('href', new RegExp(`//${slug}\\.`));

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
  await expect(page.locator('ion-button', { hasText: 'Back to my demo' })).toHaveCount(0);
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

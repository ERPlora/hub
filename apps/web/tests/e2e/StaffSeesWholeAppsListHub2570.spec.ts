// Regression test for ERPlora/hub#2570 — on a phone, someone who does not run the hub (an employee,
// a cashier) opened Apps › My apps and the list card came out cut at the bottom: «You have no apps
// yet…» stopped halfway and the footer with the record count was gone. An admin, on the same phone,
// saw it whole.
//
// The difference is the info note only that person gets above the list («You can see the apps, but
// only an administrator can install them…»): it eats the height the `fill` table had, and the table
// boxed its toolbar, its empty state and its footer into what was left (227 px of a 289 px card,
// clipped). The cure lives in OutfitKit (ERPlora/outfitkit#218, v0.1.109): on a phone a `fill` list
// is as tall as its content and scrolls WITH the page, like Shopify, Square or Odoo. This bench (and
// every hub image) installs `@erplora/outfitkit@latest`, so this spec is the hub's half: the Apps
// screen, as that person sees it, never clips its list again, whatever OutfitKit ships next.
//
// It needs a REAL session that does not administer the hub — the runtime decides who is an admin,
// nothing here fakes it — and, on a phone, the blocking strip of a hub with no business identity on
// top, which is the report's screen (the strip also takes height).
//
// 🔴 The file name is load-bearing: it sorts AFTER `ShellVisual.spec.ts`. The person it creates
// cannot be deleted —the core's removal is deactivating, and `/employees` paints inactive rows too
// (see `UsersCrudTestids.spec.ts`)— so no visual contract may run after it.
import type { Locator, Page } from '@playwright/test';
import { test, expect, request as pwRequest } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';
import { VIEWPORTS } from './viewports';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

// Spanish on purpose: its copy is the longest the note and the empty state have to hold, and it is
// the report's.
test.use({ locale: 'es-ES' });

/** Prefix of the person this spec creates. Also its clean-up tag. */
const PREFIX = 'QA Apps Viewer ';
/** A PIN this bench accepts: six digits, no progression (`isGuessablePin` refuses 123456). */
const PIN = '742958';

/** The UI contract's three sizes, the low phone of the report and the narrowest phone there is. */
const SIZES = [...VIEWPORTS, { width: 375, height: 667 }, { width: 320, height: 568 }] as const;

interface HubUser {
  id: string;
  name: string;
  is_active?: boolean;
}

async function hubApi<T>(token: string, method: 'GET' | 'POST' | 'DELETE', path: string, data?: unknown): Promise<T> {
  const api = await pwRequest.newContext();
  const res = await api.fetch(`${RUNTIME}${path}`, { method, data, headers: { 'X-Hub-Session': token } });
  const text = await res.text();
  await api.dispose();
  expect(res.ok(), `${method} ${path}: ${res.status()} ${text}`).toBeTruthy();
  return (JSON.parse(text) as { data: T }).data;
}

/**
 * The bench database outlives a run, and a PIN only opens the session of an ACTIVE person: a run
 * that died before its clean-up would leave this PIN taken and the next one red for the wrong reason.
 */
async function deactivateLeftovers(adminToken: string): Promise<void> {
  const users = await hubApi<HubUser[]>(adminToken, 'GET', '/api/hub/users');
  for (const user of users.filter((u) => u.name.startsWith(PREFIX) && u.is_active !== false)) {
    await hubApi(adminToken, 'DELETE', `/api/hub/users/${user.id}`);
  }
}

/** «My apps» is the first `ok-data-table` of the page (the catalog is the second). */
const myApps = (page: Page): Locator => page.locator('ok-data-table').first();

/** How far the list's card hides its own content: 0 when everything in it is laid out in view. */
async function clippedPx(table: Locator): Promise<number> {
  return table.evaluate((host) => {
    const card = host.shadowRoot?.querySelector<HTMLElement>('.card');
    if (!card) throw new Error('ok-data-table has no card');
    return card.scrollHeight - card.clientHeight;
  });
}

/**
 * Scrolls the page to its end the way a thumb would —wheel steps over the page, never a scripted
 * `scrollToBottom()`, which also moves a page the person cannot scroll— and returns where the
 * tabbar starts.
 */
async function scrollToEnd(page: Page): Promise<number> {
  const content = await page.locator('.ion-page:not(.ion-page-hidden) > ion-content').boundingBox();
  const footer = await page.locator('.ion-page:not(.ion-page-hidden) > ion-footer').boundingBox();
  if (!content || !footer) throw new Error('Apps is not laid out');
  await page.mouse.move(content.x + content.width / 2, content.y + content.height / 2);
  for (let step = 0; step < 8; step += 1) await page.mouse.wheel(0, 400);
  return footer.y;
}

/** Where a piece of the list ends on screen right now. */
async function bottomOf(target: Locator, what: string): Promise<number> {
  const box = await target.boundingBox();
  if (!box) throw new Error(`${what} is not laid out`);
  return box.y + box.height;
}

test.describe('My apps, seen by someone who does not run the hub (hub#2570)', () => {
  let viewer: HubUser;
  let adminToken: string;

  test.beforeAll(async () => {
    adminToken = (await loginByPin()).token;
    await deactivateLeftovers(adminToken);
    viewer = await hubApi<HubUser>(adminToken, 'POST', '/api/hub/users', {
      name: `${PREFIX}${Date.now()}`,
      email: '',
      role: 'employee',
      pin: PIN,
      local: true,
    });
  });

  test.afterAll(async () => {
    if (viewer) await hubApi(adminToken, 'DELETE', `/api/hub/users/${viewer.id}`);
  });

  for (const viewport of SIZES) {
    test(`${viewport.width}×${viewport.height}: the empty list and its footer are read whole under the admin-only note`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport);
      const api = await pwRequest.newContext();
      const res = await api.post(`${RUNTIME}/api/auth/pin`, {
        data: { name: viewer.name, pin: PIN, device_id: 'e2e-browser-device' },
      });
      expect(res.ok(), `employee PIN login: ${res.status()} ${await res.text()}`).toBeTruthy();
      const session = await res.json();
      await api.dispose();
      await withSession(page, { token: session.token, user: session.user });

      await page.goto('/apps');
      // The report's screen: the note only someone who does not run the hub gets, above the list.
      await expect(page.getByText('Puedes ver las apps, pero solo un administrador puede instalarlas')).toBeVisible();
      const table = myApps(page);
      const empty = table.getByText('Aún no tienes apps.');
      await expect(empty, 'the runtime answered: this hub has no apps').toBeVisible();
      const pager = table.locator('.pager');

      await expect.poll(() => clippedPx(table), 'the list’s card hides none of its own content').toBeLessThanOrEqual(1);

      const tabbarTop = await scrollToEnd(page);
      for (const [what, target] of [
        ['the empty state', empty],
        ['the footer', pager],
      ] as const) {
        // The wheel does not wait for the scroll it starts: poll until the page has come to rest.
        await expect
          .poll(() => bottomOf(target, what), `${what} ends above the tabbar once the page is scrolled to its end`)
          .toBeLessThanOrEqual(tabbarTop + 0.5);
        const box = await target.boundingBox();
        expect(box?.y ?? -1, `${what} starts on screen`).toBeGreaterThanOrEqual(0);
      }
    });
  }
});

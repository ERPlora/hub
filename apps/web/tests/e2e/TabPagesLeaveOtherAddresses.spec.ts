// hub#2444 — a link from Settings or Employees to a System tab opened System → Resources.
//
// Ionic keeps every visited page mounted and the shell has ONE route, so each tabbed page's
// tab ↔ hash sync used to read the next page's hash as one of its own tabs and write its default
// back: `/settings#tickets` → `/system#updates` ended on `/system#hub` (Resources), and
// `/employees#roles` on `/system#resources`; Billing and Dashboard did it from any non-default tab,
// and Apps flipped itself back to «My apps» behind the scenes. The unit tests pin `useHashTab` and
// the pattern; this is the symptom on the real shell, with Ionic keeping the pages mounted.
import { test, expect, type Page } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';

interface ShellRouter {
  push: (p: string) => Promise<unknown>;
  back: () => void;
  currentRoute: { value: { fullPath: string; path: string } };
}

function currentRoute(page: Page): Promise<{ fullPath: string; path: string }> {
  return page.evaluate(() => {
    const { fullPath, path } = (
      document.querySelector('#app') as unknown as {
        __vue_app__: { config: { globalProperties: { $router: ShellRouter } } };
      }
    ).__vue_app__.config.globalProperties.$router.currentRoute.value;
    return { fullPath, path };
  });
}

/** Ionic finished the page transition: exactly one page of the outlet is on screen. */
async function settled(page: Page): Promise<void> {
  await expect(page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)')).toHaveCount(1);
}

/** In-app navigation, the way a link inside the shell does it — the page left behind stays mounted.
 *  The promise stays in the page (hub#2100); what it stood for is read from outside. */
async function go(page: Page, to: string): Promise<void> {
  const path = to.split('#')[0];
  await page.evaluate((target) => {
    void (
      document.querySelector('#app') as unknown as {
        __vue_app__: { config: { globalProperties: { $router: ShellRouter } } };
      }
    ).__vue_app__.config.globalProperties.$router.push(target);
  }, to);
  await expect.poll(async () => (await currentRoute(page)).path).toBe(path);
  await settled(page);
}

/** The tab the page on screen shows: its tab bar's value. */
function shownTab(page: Page): Promise<string> {
  return page
    .locator('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-segment.ok-tabbar')
    .first()
    .evaluate((el) => String((el as HTMLElement & { value?: unknown }).value));
}

/** Nothing rewrites the address after landing: give the watchers of every mounted page their turn. */
async function addressStays(page: Page, fullPath: string): Promise<void> {
  await page.waitForTimeout(500);
  expect((await currentRoute(page)).fullPath).toBe(fullPath);
}

test.describe('a link to a System tab opens that tab, from any tabbed page (hub#2444)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loggedInSession(page);
  });

  for (const from of [
    '/settings#tickets',
    '/employees#roles',
    '/billing#payments',
    '/dashboard#actividad',
    '/apps#all',
  ]) {
    test(`from ${from}`, async ({ page }) => {
      await page.goto(from);
      await settled(page);
      await expect.poll(() => shownTab(page)).toBe(from.split('#')[1]);

      await go(page, '/system#updates');
      await addressStays(page, '/system#updates');
      expect(await shownTab(page)).toBe('updates');

      // And the page left behind did not flip itself: back on it, its tab is still there.
      await page.goBack();
      await settled(page);
      await addressStays(page, from);
      expect(await shownTab(page)).toBe(from.split('#')[1]);
    });
  }

  test('a tabbed page still follows a link to another of its own tabs', async ({ page }) => {
    await page.goto('/settings#tickets');
    await settled(page);
    await go(page, '/settings#permissions');
    await addressStays(page, '/settings#permissions');
    expect(await shownTab(page)).toBe('permissions');
  });

  test('a retired Settings hash still lands on the tab it became', async ({ page }) => {
    await page.goto('/settings#tax');
    await settled(page);
    await expect.poll(async () => (await currentRoute(page)).fullPath).toBe('/settings#business');
    expect(await shownTab(page)).toBe('business');
  });
});

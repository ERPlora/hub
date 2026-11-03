// FIX-SHELL-NAV (PLAN-MIGRATIONS §13) → FIX-SHELL-SPLIT-PANE (§16, Ioan 2026-10-17): the hub's shell is the old
// hub's, side menu included. Moving between apps: the ⠿ «My apps» sheet and Home (the first entry of the
// side menu, pinned from 992 px and a drawer below); no Back on the screens of a module; the sections of
// an app stay in its bottom tabbar. The menu, the rail and the drawer themselves: shell-split-pane.spec.ts.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { type Locator, type Page, expect, test } from '@playwright/test';

import { customersReady } from './customer-helpers';
import { A, createItem, HUB_DIR, listReady, login, openApps, record, shot, shown, topbarApps, uniqueName } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

type Box = { x: number; y: number; width: number; height: number };

const overlaps = (a: Box, b: Box): boolean =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

/** The topbar of the screen on view and its pieces: the way to the menu (drawer or rail), the title, Back and the apps. */
function topbar(page: Page): Record<'title' | 'drawer' | 'rail' | 'back' | 'apps', Locator> {
  const bar = shown(page).locator('ion-header.app-topbar');
  return {
    title: bar.locator('ion-title'),
    drawer: bar.locator('ion-menu-button'),
    rail: bar.locator('[data-testid=topbar-rail]'),
    back: bar.locator('[data-testid=topbar-back]'),
    apps: bar.locator('[data-testid=topbar-apps]'),
  };
}

/** Home, from the side menu: pinned from 992 px, through the hamburger's drawer below. */
async function goHomeFromMenu(page: Page): Promise<void> {
  const home = page.locator('ion-menu.dash-menu [data-testid=nav-home]');
  if (!(await home.isVisible())) await topbar(page).drawer.click();
  await home.click();
}

/** Enabled tiles of the sheet other than Demo (the app the specs start in). */
const otherApps = (sheet: Locator): Locator =>
  sheet.locator('[data-testid=apps-launcher-app]:not([disabled])').filter({ hasNotText: /^\s*Demo\s*$/ });

test('390 / 834 / 1440: the way to the menu, the ⠿ apps and no Back in the topbar, clear of the title', async ({ page }) => {
  await login(page, A);
  const results: Record<string, unknown> = {};
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    // The root of an app with sections (Customers, the old hub's reference screen).
    await page.goto('/customer/customers');
    const bar = topbar(page);
    // hub#1831: the way to the menu is there on the first paint: the drawer's below lg, the rail's from lg.
    const menuDoor = vp.width >= 992 ? bar.rail : bar.drawer;
    for (const piece of [menuDoor, bar.apps]) await expect(piece).toBeVisible();
    await expect(vp.width >= 992 ? bar.drawer : bar.rail).toBeHidden();
    await expect(bar.back).toHaveCount(0);
    await customersReady(page);
    await page.waitForTimeout(400);

    // hub#690: on a phone (ios) the icons covered the title.
    const title = (await bar.title.boundingBox())!;
    const boxes = { menu: (await menuDoor.boundingBox())!, apps: (await bar.apps.boundingBox())! };
    results[vp.label] = { title, ...boxes };
    for (const [name, box] of Object.entries(boxes)) {
      expect(overlaps(title, box), `${vp.label}: the title runs over ${name}`).toBe(false);
      expect(box.x + box.width, `${vp.label}: ${name} inside the screen`).toBeLessThanOrEqual(vp.width);
    }
    expect(boxes.menu.x, `${vp.label}: the menu door on the left`).toBeLessThan(title.x);
    expect(boxes.apps.x, `${vp.label}: apps on the right`).toBeGreaterThan(title.x);
    // The sections of the app are its bottom tabbar.
    await expect(shown(page).locator('ion-footer ion-segment-button').first()).toBeVisible();
    await page.screenshot({ path: shot(`FIX-SHELL-NAV-${vp.label}`) });

    if (vp.label === '390') {
      const sheet = await openApps(page);
      await expect(sheet.locator('ion-title')).toBeVisible();
      await page.waitForTimeout(500); // the sheet's slide-in
      await page.screenshot({ path: shot('FIX-SHELL-NAV-apps-390') });
      await sheet.locator('[data-testid=apps-launcher-close]').click();
      await expect(sheet).toHaveCount(0);
    }
  }
  record('FIX-SHELL-NAV-topbar', results);
});

for (const vp of [VIEWPORTS[0], VIEWPORTS[2]]) {
  test(`${vp.label}: from the root of an app opened by a link, the menu's Home goes Home; Home paints the apps`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await login(page, A);
    await page.goto('/demo/items'); // a link straight into the app: no history to go back to
    await listReady(page);
    await goHomeFromMenu(page);
    await expect(page).toHaveURL(`${A}/`);
    await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
    await expect(topbar(page).back).toHaveCount(0);
    await expect(topbar(page).apps).toBeVisible();
  });
}

test('the «My apps» sheet opens another app, and closes', async ({ page }) => {
  await login(page, A);
  await page.goto('/demo/items');
  await listReady(page);
  const sheet = await openApps(page);
  const target = otherApps(sheet).first();
  const name = (await target.getAttribute('title'))!;
  await target.click();
  await expect(sheet).toHaveCount(0);
  await expect(page).not.toHaveURL(/\/demo\//);
  await expect(topbar(page).apps).toBeVisible();
  await expect(topbar(page).back).toHaveCount(0);
  record('FIX-SHELL-NAV-open-app', { opened: name, url: page.url() });
});

// hub#2242 / hub#2241: going to an app and back fast left the address and the page out of step, or
// the page stuck on its skeleton. Back to Home is the menu's Home now (pinned at this width).
test('apps and Home, fast and repeated: the address and the page stay in step', async ({ page }) => {
  await login(page, A, '/');
  await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
  for (let round = 0; round < 4; round += 1) {
    const sheet = await openApps(page);
    await sheet.locator('[data-testid=apps-launcher-app]', { hasText: 'Demo' }).click();
    await page.locator('ion-menu.dash-menu [data-testid=nav-home]').click();
  }
  await expect(page).toHaveURL(`${A}/`);
  await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
  await expect(page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)')).toHaveCount(1);

  const sheet = await openApps(page);
  await sheet.locator('[data-testid=apps-launcher-app]', { hasText: 'Demo' }).click();
  await expect(page).toHaveURL(`${A}/demo/items`);
  await listReady(page);
  await expect(page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)')).toHaveCount(1);
});

// hub#2489 / hub#2325: with a flaky network, tapping an app opened nothing and said nothing. Since gh:hub#438 the
// notice is the shell router's, for every way of opening a screen (`view-load.ts` of @erplora/ui): the browser still
// says «online» here, the server does not answer for the file, so the screen stays and the notice names the app.
test('an app whose page does not load says so, with a Retry; never silent', async ({ page }) => {
  await login(page, A);
  await page.goto('/demo/items');
  await listReady(page);
  await page.route(/\/frontend\/pages\//, (route) => route.abort('internetdisconnected'));
  const sheet = await openApps(page);
  // Customers, whose root screen is known: Retry has to land there.
  const target = otherApps(sheet).filter({ hasText: /^\s*Customers\s*$/ });
  const name = (await target.getAttribute('title'))!;
  await target.click();
  const toast = page.locator('ion-toast#view-load-failed');
  await expect(toast).toBeVisible();
  await expect(toast).toContainText(name);
  await expect(page).toHaveURL(`${A}/demo/items`);
  await page.screenshot({ path: shot('FIX-SHELL-NAV-open-failed-390') });

  // The network is back: the toast's Retry opens the app and the toast goes away.
  await page.unroute(/\/frontend\/pages\//);
  await toast.locator('button', { hasText: /retry|reintentar/i }).click();
  await expect(page).toHaveURL(`${A}/customer/customers`);
  await customersReady(page);
  await expect(topbarApps(page)).toBeVisible();
  await expect(toast).toBeHidden();
});

// flow: BASE-F05 (Abrir una app desde «Mis apps»): a screen of an app has no Back (PLAN-MIGRATIONS §16), so the way out
// of an app is the ⠿ «My apps» sheet, and its first entry is «Home». Every app with screens (`apps/*/frontend/routes.ts`,
// read here, not a list kept by hand) is opened from the sheet, the way a person does, at the three widths: its root is
// one of its routes, it has the ⠿ apps and no Back, and every time the sheet opens «Home» comes first.

/** Each app with screens: its folder and the paths its `frontend/routes.ts` declares. */
function appsWithScreens(): Map<string, string[]> {
  const apps = new Map<string, string[]>();
  for (const id of readdirSync(join(HUB_DIR, 'apps')).sort()) {
    const file = join(HUB_DIR, 'apps', id, 'frontend', 'routes.ts');
    if (!existsSync(file)) continue;
    apps.set(id, [...readFileSync(file, 'utf8').matchAll(/\bpath:\s*['"`]([^'"`]+)['"`]/g)].map((match) => match[1]));
  }
  return apps;
}

type MenuSection = { id: string; label: string; items: { path: string }[] };

/** The person's menu as the Hub embeds it in the page (`base.session.me`, `#session-me`): one section per app. */
async function menuSections(page: Page): Promise<MenuSection[]> {
  const me = await page.evaluate(() => JSON.parse(document.getElementById('session-me')?.textContent ?? 'null'));
  return (me as { menu: MenuSection[] }).menu;
}

const homeFirst = async (sheet: Locator): Promise<void> => {
  const first = sheet.locator('.apps-launcher-app').first();
  await expect(first).toHaveAttribute('data-testid', 'apps-launcher-home');
  await expect(first).toHaveText(/^\s*(Home|Inicio)\s*$/);
};

test('the apps with screens are read from their routes, and there are some', () => {
  // A broken read (a moved folder, a renamed file) would make the walk below check nothing and pass.
  const apps = appsWithScreens();
  expect(apps.size).toBeGreaterThan(20);
  expect(apps.get('demo')).toContain('/demo/items');
});

for (const vp of VIEWPORTS) {
  test(`${vp.label}: BASE-F05 every app opened from «My apps» has the ⠿ apps and no Back on its root, and the sheet starts with «Home»`, async ({ page }) => {
    test.setTimeout(360_000);
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await login(page, A, '/');
    await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
    const sections = await menuSections(page);
    const roots: Record<string, string> = {};

    for (const [id, paths] of appsWithScreens()) {
      const section = sections.find((candidate) => candidate.id === id);
      expect(section, `${id} has screens and no tile in «My apps»`).toBeDefined();
      // Where its tile opens: the first entry of its menu section (`my-apps.ts`), one of its own routes.
      const root = section!.items[0].path;
      expect(paths, `${id}: its root ${root} is one of its routes`).toContain(root);

      const sheet = await openApps(page);
      await homeFirst(sheet);
      await sheet.locator(`[data-testid=apps-launcher-app][title="${section!.label}"]`).click();
      await expect(sheet).toHaveCount(0);
      // A root may hand over to its first section (`/inventory` → `/inventory/dashboard`): still one of the app's routes.
      await expect(page).toHaveURL((url) => url.pathname === root || url.pathname.startsWith(`${root}/`));
      const landed = new URL(page.url()).pathname;
      expect(paths, `${id}: it lands on ${landed}, one of its routes`).toContain(landed);
      const bar = topbar(page);
      await expect(bar.apps, `${vp.label} ${id} ${landed}: the ⠿ apps`).toBeVisible();
      await expect(bar.back, `${vp.label} ${id} ${landed}: no Back on the root of an app`).toHaveCount(0);
      roots[id] = landed;
    }

    // The way out, seen: the root of Customers (the old hub's reference screen) with the sheet open, «Home» first.
    await page.goto('/customer/customers');
    await customersReady(page);
    const sheet = await openApps(page);
    await homeFirst(sheet);
    await page.waitForTimeout(500); // the sheet's slide-in
    await page.screenshot({ path: shot(`FIX-HUB-BASE-APPS-BUTTON-AND-ANDROID-BACK-FROM-APP-ROOT-${vp.label}`) });

    // «Home» leaves the app.
    await sheet.locator('[data-testid=apps-launcher-home]').click();
    await expect(sheet).toHaveCount(0);
    await expect(page).toHaveURL(`${A}/`);
    await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
    record(`BASE-F05-app-roots-${vp.label}`, roots);
  });
}

// flow: BASE-F05 · gh:hub#1906 — Android's Back button. Tauri does not run in Playwright: the installed app's bridge is
// simulated at the edge (`window.__TAURI__`, which records what it is asked and keeps the listener the shell registers
// on the `app` plugin's `back-button`, what Tauri's `onBackButtonPress` listens to); a press calls that listener, as the
// app does. Hub, SaaS and the screens are the real ones.

type BackBridge = { asked: string[]; listeners: ((payload: unknown) => Promise<void>)[] };

/** From the next page load on, the page runs inside the installed app (after the login, which is the SaaS's page). */
async function insideTheApp(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const bridge: BackBridge = { asked: [], listeners: [] };
    const win = window as unknown as { __TAURI__: unknown; __back: BackBridge };
    win.__back = bridge;
    win.__TAURI__ = {
      core: {
        invoke: async (command: string) => {
          bridge.asked.push(command);
          return null;
        },
        addPluginListener: async (plugin: string, event: string, listener: (payload: unknown) => Promise<void>) => {
          if (plugin === 'app' && event === 'back-button') bridge.listeners.push(listener);
          return {
            unregister: async () => {
              bridge.listeners = bridge.listeners.filter((kept) => kept !== listener);
            },
          };
        },
      },
    };
  });
}

/** One press of the Back button, on the one listener the shell holds. */
async function pressBack(page: Page): Promise<void> {
  const held = () => page.evaluate(() => (window as unknown as { __back: BackBridge }).__back.listeners.length);
  await expect.poll(held, { message: 'the shell holds the Back button' }).toBe(1);
  await page.evaluate(() => (window as unknown as { __back: BackBridge }).__back.listeners[0]({ canGoBack: false }));
}

const leftTheApp = (page: Page): Promise<boolean> =>
  page.evaluate(() => (window as unknown as { __back: BackBridge }).__back.asked.includes('plugin:erplora-android|leave_app'));

test('BASE-F05 gh:hub#1906: Back on the root of an app opened cold goes Home, and only Home leaves the app', async ({ page }) => {
  await login(page, A);
  await insideTheApp(page);
  await page.goto('/demo/items'); // cold: a link or a reload straight into the app
  await listReady(page);

  await pressBack(page);
  await expect(page).toHaveURL(`${A}/`);
  await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
  expect(await leftTheApp(page)).toBe(false);

  await pressBack(page);
  await expect.poll(() => leftTheApp(page)).toBe(true);
  await expect(page).toHaveURL(`${A}/`);
});

test('BASE-F05 gh:hub#1906: Back with «My apps» open closes the sheet, and the screen stays', async ({ page }) => {
  await login(page, A);
  await insideTheApp(page);
  await page.goto('/demo/items');
  await listReady(page);
  const sheet = await openApps(page);

  await pressBack(page);
  await expect(sheet).toHaveCount(0);
  await expect(page).toHaveURL(`${A}/demo/items`);
  await expect(topbar(page).apps).toBeVisible();
  expect(await leftTheApp(page)).toBe(false);
});

test('BASE-F05 gh:hub#1906: Back with the drawer open (390) closes it, and the screen stays', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, A);
  await insideTheApp(page);
  await page.goto('/demo/items');
  await listReady(page);
  await topbar(page).drawer.click();
  const menu = page.locator('ion-menu.dash-menu');
  // Open, as a person sees it: a press while it still slides in holds (lib/system-back.test.ts).
  await expect.poll(() => menu.evaluate((element) => (element as HTMLElement & { isOpen: () => Promise<boolean> }).isOpen())).toBe(true);

  await pressBack(page);
  await expect(menu.locator('[data-testid=nav-home]')).toBeHidden();
  await expect(page).toHaveURL(`${A}/demo/items`);
});

test('BASE-F05 gh:hub#1906: Back on a detail view opened cold is its own Back, to the list', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('Android Back item'));
  await insideTheApp(page);
  await page.goto(`/demo/items/${item.id}`);
  await expect(page.locator('[data-testid=demo-detail-status]')).toBeVisible();
  await expect(topbar(page).back).toBeVisible();

  await pressBack(page);
  await expect(page).toHaveURL(`${A}/demo/items`);
  await listReady(page);
  expect(await leftTheApp(page)).toBe(false);
});

// flow: SALE-F01 · FIX-HUB-SALE-POS-MORE-MENU-ANDROID-BACK-GOES-HOME — Android's Back on the till of the installed app.
// The till's own layers (the ⋮ screen menu, «Open checks», the phone's check drawer) are sheets of the app, not Ionic
// overlays: they answer base's `erplora:back` (base/frontend/lib/system-back.ts), so Back closes the topmost one and
// the till stays; with nothing open, Back is the shell's (the root of an app goes Home). Tauri does not run in
// Playwright: the installed app's bridge is simulated at the edge as in shell-nav.spec.ts (`window.__TAURI__`, which
// keeps the listener the shell registers on the `app` plugin's `back-button`); a press calls that listener, as the app
// does. Hub, SaaS and the till are the real ones; nothing is written.
import { expect, type Page, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
import { openTillCart } from './sale-helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

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

/** The till of the installed app, opened cold (a link or a reload straight into it). */
async function tillInsideTheApp(page: Page): Promise<void> {
  await login(page, A);
  await insideTheApp(page);
  await page.goto('/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid^=pos-product-], [data-testid=pos-grid-empty]').first().waitFor({ state: 'visible' });
}

for (const vp of VIEWPORTS) {
  test(`SALE-F01 ${vp.label}: Back with the ⋮ screen menu open closes it and the till stays; the next Back goes Home`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await tillInsideTheApp(page);
    const trigger = shown(page).locator('[data-testid=pos-screen-menu]');
    await trigger.click();
    await expect(shown(page).locator('[data-testid=pos-fullscreen]')).toBeVisible();

    await pressBack(page);
    await expect(page).toHaveURL(`${A}/sale/pos`);
    await expect(shown(page).locator('[data-testid=pos-screen-menu-list]')).toHaveCount(0);
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(shown(page).locator('[data-testid=pos-till]')).toBeVisible();
    expect(await leftTheApp(page)).toBe(false);
    await page.screenshot({ path: shot(`FIX-HUB-SALE-POS-MORE-MENU-ANDROID-BACK-GOES-HOME-${vp.label}`) });

    // Nothing of the till open: the shell's rule, the root of an app goes Home.
    await pressBack(page);
    await expect(page).toHaveURL(`${A}/`);
    await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
    expect(await leftTheApp(page)).toBe(false);
  });
}

test('SALE-F01 390: Back closes «Open checks» first, then the check drawer, and the till stays; then it goes Home', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await tillInsideTheApp(page);
  const till = shown(page).locator('[data-testid=pos-till]');
  await openTillCart(page);
  await shown(page).locator('[data-testid=pos-open-checks]').click();
  const checks = shown(page).locator('[data-testid=pos-checks]');
  await expect(checks).toBeVisible();

  await pressBack(page);
  await expect(page).toHaveURL(`${A}/sale/pos`);
  await expect(checks).toHaveCount(0);
  await expect(till).toHaveClass(/pos-till--cart-open/);

  await pressBack(page);
  await expect(till).not.toHaveClass(/pos-till--cart-open/);
  await expect(page).toHaveURL(`${A}/sale/pos`);
  expect(await leftTheApp(page)).toBe(false);

  await pressBack(page);
  await expect(page).toHaveURL(`${A}/`);
  expect(await leftTheApp(page)).toBe(false);
});

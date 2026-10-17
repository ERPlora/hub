// FIX-SHELL-SPLIT-PANE (PLAN-MIGRATIONS §16, Ioan 2026-10-17): the hub's shell is the old hub's, side menu
// included (docs/reference/old-hub/{dashboard,menu-toggle,verifactu-settings}-*.png). The menu is pinned
// from 992 px and the topbar folds it to a rail of icons; below, a drawer the hamburger opens. In it, the
// person, the platform's entries whose screen exists (today Home only) and no module; in its footer, the
// QR «Open on your phone». The topbar: drawer button or rail toggle, the title centred, the ⠿ «My apps»;
// no Back on the screens of a module nor on Home (only on a detail, as in the old hub).
// flow: ninguno — FIX shell
import { type Locator, type Page, expect, test } from '@playwright/test';

import { customersReady } from './customer-helpers';
import { A, createItem, listReady, login, openApps, record, shot, shown, uniqueName } from './helpers';

const VIEWPORTS = {
  phone: { label: '390', width: 390, height: 844 },
  tablet: { label: '834', width: 834, height: 1112 },
  desktop: { label: '1440', width: 1440, height: 900 },
} as const;

type Box = { x: number; y: number; width: number; height: number };

const menu = (page: Page): Locator => page.locator('ion-menu.dash-menu');
const entries = (page: Page): Locator => menu(page).locator('ion-item.nav-item');

/** The topbar of the screen on view and its pieces. */
function topbar(page: Page) {
  const bar = shown(page).locator('ion-header.app-topbar');
  return {
    toolbar: bar.locator('ion-toolbar'),
    title: bar.locator('ion-title'),
    drawer: bar.locator('ion-menu-button'),
    rail: bar.locator('[data-testid=topbar-rail]'),
    back: bar.locator('[data-testid=topbar-back]'),
    apps: bar.locator('[data-testid=topbar-apps]'),
  };
}

/** The title's text, centred on its bar (the old hub's ios title), within 4 px. */
async function expectTitleCentred(page: Page, label: string): Promise<{ title: Box; toolbar: Box }> {
  const bar = topbar(page);
  const text = await bar.title.evaluate((el) => {
    const inner = el.shadowRoot?.querySelector('.toolbar-title') ?? el;
    const range = document.createRange();
    range.selectNodeContents(inner);
    const box = (range.getClientRects().length ? range : inner).getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  });
  const toolbar = (await bar.toolbar.boundingBox())!;
  const centre = (box: Box) => box.x + box.width / 2;
  expect(Math.abs(centre(text) - centre(toolbar)), `${label}: the title is centred`).toBeLessThanOrEqual(4);
  return { title: text, toolbar };
}

test('1440: the menu pinned next to the content, the person on top and the QR below; the topbar folds it to a rail and back', async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await login(page, A);
  await page.goto('/demo/items');
  await listReady(page);

  await expect(menu(page)).toBeVisible();
  await expect(page.locator('ion-split-pane')).toHaveClass(/split-pane-visible/);
  const pinned = (await menu(page).boundingBox())!;
  const content = (await page.locator('ion-router-outlet#main').boundingBox())!;
  expect(pinned.x).toBe(0);
  expect(pinned.width).toBeGreaterThanOrEqual(232);
  expect(pinned.width).toBeLessThanOrEqual(248);
  expect(content.x, 'the content starts where the menu ends, not under it').toBeGreaterThanOrEqual(pinned.x + pinned.width - 1);

  // The person at the top; Home, the only platform entry with a screen today; no module.
  await expect(menu(page).locator('[data-testid=user-menu-trigger] .sidebar-user-name')).toBeVisible();
  await expect(entries(page)).toHaveCount(1);
  expect(await entries(page).evaluateAll((items) => items.map((item) => item.getAttribute('data-testid')))).toEqual(['nav-home']);
  const qr = menu(page).locator('[data-testid=sidebar-install-qr] img.sidebar-install-qr-code');
  await expect(qr).toBeVisible();
  expect(await qr.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await expect(menu(page).locator('.sidebar-install-qr-title')).toHaveText('Open on your phone');

  // The topbar: the rail toggle where the hamburger was, the ⠿ apps, no Back in a module.
  const bar = topbar(page);
  await expect(bar.drawer).toBeHidden();
  await expect(bar.rail).toBeVisible();
  await expect(bar.apps).toBeVisible();
  await expect(bar.back).toHaveCount(0);
  const centred = await expectTitleCentred(page, '1440');
  await page.screenshot({ path: shot('FIX-SHELL-SPLIT-PANE-1440-module') });

  // Folded to a rail: icons only, the QR's icon instead of the code; unfolded again. The toggle says
  // which it does (Ionic moves `aria-label` into its inner button: the name is what a reader hears).
  const railNamed = (name: string) => shown(page).locator('ion-header.app-topbar').getByRole('button', { name, exact: true });
  await expect(railNamed('Collapse menu')).toBeVisible();
  await bar.rail.click();
  await expect(page.locator('ion-split-pane')).toHaveClass(/\brail\b/);
  await expect.poll(async () => (await menu(page).boundingBox())!.width).toBe(68);
  await expect(menu(page).locator('[data-testid=nav-home] .nav-label')).toBeHidden();
  await expect(menu(page).locator('[data-testid=nav-home] .nav-icon')).toBeVisible();
  await expect(qr).toBeHidden();
  await expect(menu(page).locator('ion-button.sidebar-install-qr-rail')).toBeVisible();
  await expect(railNamed('Expand menu')).toBeVisible();
  await expect(railNamed('Collapse menu')).toHaveCount(0);
  await page.waitForTimeout(400); // the width transition
  await page.screenshot({ path: shot('FIX-SHELL-SPLIT-PANE-1440-rail') });

  await bar.rail.click();
  await expect(page.locator('ion-split-pane')).not.toHaveClass(/\brail\b/);
  await expect(railNamed('Collapse menu')).toBeVisible();
  await expect.poll(async () => (await menu(page).boundingBox())!.width).toBe(pinned.width);
  await expect(menu(page).locator('[data-testid=nav-home] .nav-label')).toBeVisible();
  await expect(qr).toBeVisible();

  // Home, from the menu.
  await menu(page).locator('[data-testid=nav-home]').click();
  await expect(page).toHaveURL(`${A}/`);
  await expect(shown(page).locator('[data-testid=home-app]').first()).toBeVisible();
  await expect(menu(page).locator('[data-testid=nav-home]')).toHaveAttribute('aria-current', 'page');
  await page.waitForTimeout(400);
  await page.screenshot({ path: shot('FIX-SHELL-SPLIT-PANE-1440') });
  record('FIX-SHELL-SPLIT-PANE-1440', { menu: pinned, content, ...centred });
});

for (const vp of [VIEWPORTS.tablet, VIEWPORTS.phone]) {
  test(`${vp.label}: no menu at the side; the hamburger opens the drawer and picking an entry closes it`, async ({ page }) => {
    await page.setViewportSize(vp);
    await login(page, A);
    await page.goto('/demo/items');
    await listReady(page);

    await expect(menu(page)).toBeHidden();
    await expect(page.locator('ion-split-pane')).not.toHaveClass(/split-pane-visible/);
    const bar = topbar(page);
    await expect(bar.drawer).toBeVisible();
    await expect(bar.rail).toBeHidden();
    await expect(bar.apps).toBeVisible();
    await expect(bar.back).toHaveCount(0);
    const centred = await expectTitleCentred(page, vp.label);
    await page.screenshot({ path: shot(`FIX-SHELL-SPLIT-PANE-${vp.label}-module`) });

    await bar.drawer.click();
    await expect(menu(page)).toBeVisible();
    await expect(menu(page).locator('[data-testid=user-menu-trigger] .sidebar-user-name')).toBeVisible();
    expect(await entries(page).evaluateAll((items) => items.map((item) => item.getAttribute('data-testid')))).toEqual(['nav-home']);
    await expect(menu(page).locator('[data-testid=nav-home] .nav-label')).toBeVisible();
    await expect(menu(page).locator('[data-testid=sidebar-install-qr] img.sidebar-install-qr-code')).toBeVisible();
    await page.waitForTimeout(500); // the drawer's slide-in
    if (vp.label === '390') await page.screenshot({ path: shot('FIX-SHELL-SPLIT-PANE-390-drawer') });

    await menu(page).locator('[data-testid=nav-home]').click();
    await expect(page).toHaveURL(`${A}/`);
    await expect(menu(page)).toBeHidden();
    await expect(shown(page).locator('[data-testid=home-app]').first()).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`FIX-SHELL-SPLIT-PANE-${vp.label}`) });
    record(`FIX-SHELL-SPLIT-PANE-${vp.label}`, centred);
  });
}

test('no Back on the screens of a module nor on Home, only on a detail; the ⠿ opens «My apps» at every width', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('Split pane detail'));
  for (const vp of Object.values(VIEWPORTS)) {
    await page.setViewportSize(vp);
    await page.goto('/demo/items');
    await listReady(page);
    await expect(topbar(page).back, `${vp.label}: the root of the demo`).toHaveCount(0);

    await page.goto('/customer/customers');
    await customersReady(page);
    await expect(topbar(page).back, `${vp.label}: the root of a business app`).toHaveCount(0);

    await page.goto('/');
    await expect(shown(page).locator('[data-testid=home-app]').first()).toBeVisible();
    await expect(topbar(page).back, `${vp.label}: Home`).toHaveCount(0);

    // A detail keeps its contextual Back (the old hub's `back-href`), and it returns to its list.
    await page.goto(`/demo/items/${item.id}`);
    await expect(shown(page).locator('[data-testid=demo-detail-status]')).toBeVisible();
    await topbar(page).back.click();
    await expect(page).toHaveURL(`${A}/demo/items`);

    const sheet = await openApps(page);
    await expect(sheet.locator('[data-testid=apps-launcher-app]', { hasText: 'Demo' })).toBeVisible();
    await sheet.locator('[data-testid=apps-launcher-close]').click();
    await expect(sheet).toHaveCount(0);
  }
});

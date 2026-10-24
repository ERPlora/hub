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
/** The platform's entries of the menu, in its order: the ones whose screen exists. */
const PLATFORM_ENTRIES = ['nav-home', 'nav-apps', 'nav-system'];

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

  // The person at the top; the platform entries with a screen today (Home, Apps and System: APP-BASE-4); no module.
  await expect(menu(page).locator('[data-testid=user-menu-trigger] .sidebar-user-name')).toBeVisible();
  await expect(entries(page)).toHaveCount(PLATFORM_ENTRIES.length);
  expect(await entries(page).evaluateAll((items) => items.map((item) => item.getAttribute('data-testid')))).toEqual(PLATFORM_ENTRIES);
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
  await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
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
    expect(await entries(page).evaluateAll((items) => items.map((item) => item.getAttribute('data-testid')))).toEqual(PLATFORM_ENTRIES);
    await expect(menu(page).locator('[data-testid=nav-home] .nav-label')).toBeVisible();
    await expect(menu(page).locator('[data-testid=sidebar-install-qr] img.sidebar-install-qr-code')).toBeVisible();
    await page.waitForTimeout(500); // the drawer's slide-in
    if (vp.label === '390') await page.screenshot({ path: shot('FIX-SHELL-SPLIT-PANE-390-drawer') });

    await menu(page).locator('[data-testid=nav-home]').click();
    await expect(page).toHaveURL(`${A}/`);
    await expect(menu(page)).toBeHidden();
    await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
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
    await expect(shown(page).locator('[data-testid=home-my-app]').first()).toBeVisible();
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

/** The boxes of the user menu once Ionic finished presenting it (its enter animation fades the sheet in). */
async function measureUserMenu(page: Page) {
  return page.evaluate(() => {
    const box = (el: Element) => {
      const r = el.getBoundingClientRect();
      return { left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top), bottom: Math.round(r.bottom) };
    };
    const lines = (el: Element) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
    };
    const popover = document.querySelector('ion-popover.sidebar-user-popover')!;
    const content = popover.shadowRoot!.querySelector('.popover-content')!;
    const theme = document.querySelector('[data-testid="user-menu-theme"]')!;
    const segment = theme.querySelector('ion-segment')!;
    const trigger = document.querySelector('[data-testid="user-menu-trigger"]')!;
    const text = (el: Element | null) =>
      el && { ...box(el), display: getComputedStyle(el).display, ellipsis: getComputedStyle(el).textOverflow };
    return {
      themeLabel: { ...box(theme.querySelector('ion-label')!), lines: lines(theme.querySelector('ion-label')!) },
      segment: box(segment),
      buttons: [...segment.querySelectorAll('ion-segment-button')].map((button) => box(button)),
      icons: [...segment.querySelectorAll('ion-segment-button ion-icon')].map((icon) => box(icon)),
      sheet: { ...box(content), opacity: Number(getComputedStyle(content).opacity), fill: getComputedStyle(content).backgroundColor },
      viewport: { width: innerWidth, height: innerHeight },
      card: box(trigger),
      chevron: box(trigger.querySelector('.sidebar-user-chevron')!),
      name: text(trigger.querySelector('.sidebar-user-name')),
      email: text(trigger.querySelector('.sidebar-user-email')),
    };
  });
}

// The user menu is the shared shell's (ERPlora/ui UserMenuPopover + App.vue), the SaaS's too: «Theme» went
// one letter a line, the card's name and email ran under the chevron without «…», and from the name the
// menu hung over the email line (ACCOUNTS-G93 in the SaaS, MIGRATION-TASK APP-ACCOUNTS-1).
// The three sizes of the spec and the two others of the fleet's sweep (a short phone, a portrait tablet).
const MENU_VIEWPORTS = [
  VIEWPORTS.phone,
  VIEWPORTS.tablet,
  VIEWPORTS.desktop,
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
];
for (const vp of MENU_VIEWPORTS) {
  test(`${vp.label}x${vp.height}: the user menu reads whole — «Theme» on one line, under the card, its name and email ending in «…» before the chevron`, async ({ page }) => {
    await page.setViewportSize(vp);
    await login(page, A);
    await page.goto('/demo/items');
    await listReady(page);
    if (!(await menu(page).isVisible())) {
      const opened = page.evaluate(() => new Promise<void>((resolve) => document.addEventListener('ionDidOpen', () => resolve(), { once: true })));
      await topbar(page).drawer.click();
      await opened;
    }
    const presented = page.evaluate(
      () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
    );
    // On the name: the click that used to hang the menu from the name, over the email line.
    await menu(page).locator('[data-testid=user-menu-trigger] .sidebar-user-name').click();
    await presented;
    const m = await measureUserMenu(page);
    const at = `${vp.label}: ${JSON.stringify(m)}`;
    console.log(`user menu at ${at}`);

    expect.soft(m.themeLabel.lines, `«Theme» on one line at ${at}`).toBe(1);
    expect.soft(m.themeLabel.right, `«Theme» ends before the theme buttons at ${at}`).toBeLessThanOrEqual(m.segment.left);
    m.buttons.forEach((button, i) => {
      const icon = m.icons[i];
      expect.soft(button.left >= m.segment.left && button.right <= m.segment.right, `a theme button stays in its row at ${at}`).toBe(true);
      expect.soft(Math.min(button.right - button.left, button.bottom - button.top), `a theme button is ≥ 24px at ${at}`).toBeGreaterThanOrEqual(24);
      const off = Math.abs(icon.left + icon.right - button.left - button.right) / 2;
      expect.soft(icon.left >= button.left && icon.right <= button.right && off <= 2, `a theme icon sits in the middle of its button at ${at}`).toBe(true);
    });
    expect.soft(m.sheet.opacity, `the menu is not see-through at ${at}`).toBe(1);
    expect.soft(m.sheet.fill, `the menu has an opaque fill at ${at}`).toMatch(/^rgb\(/);
    expect.soft(m.sheet.top, `the menu opens under the card, never over its email at ${at}`).toBeGreaterThanOrEqual(m.card.bottom);
    expect.soft(
      m.sheet.left >= 0 && m.sheet.right <= m.viewport.width && m.sheet.bottom <= m.viewport.height,
      `the menu is inside the window at ${at}`,
    ).toBe(true);
    for (const line of [m.name, m.email].filter((one) => one !== null)) {
      expect.soft(line.right, `the card's text stops before the chevron at ${at}`).toBeLessThanOrEqual(m.chevron.left);
      expect.soft(line.display, `the card's text is a block, so «…» can show, at ${at}`).not.toBe('inline');
      expect.soft(line.ellipsis, `the card's text ends in «…» at ${at}`).toBe('ellipsis');
    }
    await page.screenshot({ path: shot(`APP-ACCOUNTS-1-user-menu-${vp.width}x${vp.height}`), fullPage: true });
  });
}

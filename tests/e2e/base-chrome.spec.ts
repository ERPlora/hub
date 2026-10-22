// The Hub's pieces of the shell's chrome (ERPlora/ui#19), as a person sees them at 390, 834 and 1440:
// - «Upgrade plan» at the foot of the side menu (BASE-F11): lined up with the QR above it and inside the menu, and on
//   the rail (≥992 px, the menu folded to its icons) only its icon, still named, inside the 68 px;
// - the strip «You cannot invoice yet» (BASE-F01) between the bar and the screen's content, at its own height.
// No module of main declares a ⛔ step yet (Invoicing's comes with its own task), so the strip's test serves the page
// a `base.setup.status` with one pending: the live stream is answered by the test, every other query stays loading.
// flow: BASE-F01 BASE-F11
import { expect, type Locator, type Page, type Route, test } from '@playwright/test';

import { A, decodeSubs, login, shot, shown } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** The side menu is pinned from 992 px; below it is a drawer behind the bar's menu button. */
const PINNED_MIN = 992;
/** The rail's width (polish.css: `ion-split-pane.rail`). */
const RAIL = 68;

type Box = { left: number; right: number; top: number; bottom: number; height: number };

const boxOf = (locator: Locator): Promise<Box> =>
  locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, height: r.height };
  });

/** Where the QR block lays out its content: its box less its own padding. */
const contentOf = (locator: Locator): Promise<{ left: number; right: number }> =>
  locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return { left: r.left + parseFloat(style.paddingLeft), right: r.right - parseFloat(style.paddingRight) };
  });

/** How far `locator`'s content runs past its box sideways (0 = it fits). */
const sidewaysOverflow = (locator: Locator): Promise<number> =>
  locator.evaluate((el) => el.scrollWidth - el.clientWidth);

const near = (a: number, b: number) => Math.abs(a - b) <= 1;

test('BASE-F11 — «Upgrade plan» lines up with the QR at the foot of the menu; on the rail, only its icon', async ({ page }) => {
  await login(page, A, '/');
  const menu = page.locator('ion-menu');
  const foot = menu.locator('ion-footer.sidebar-foot');
  const qr = menu.locator('[data-testid="sidebar-install-qr"]');
  const link = menu.locator('[data-testid="upgrade-plan"]');

  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/`);
    if (vp.width < PINNED_MIN) await shown(page).locator('ion-menu-button').click();
    await expect(link).toBeVisible();
    await expect(link).toContainText('Upgrade plan');
    // The same inner edges as the QR above it (the drawer slides in: measured once it settled).
    await expect
      .poll(async () => {
        const [at, room] = await Promise.all([boxOf(link), contentOf(qr)]);
        return near(at.left, room.left) && near(at.right, room.right);
      }, { message: `«Upgrade plan» lined up with the QR at ${vp.label}` })
      .toBe(true);
    expect(await sidewaysOverflow(foot), `the menu's foot fits at ${vp.label}`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot(`APP-BASE-1-BASE-F11-foot-${vp.label}`) });
  }

  // On the rail (desktop only): the icon alone, named for the screen reader and the tooltip, inside the 68 px.
  const rail = shown(page).locator('[data-testid="topbar-rail"]');
  await rail.click();
  await expect(page.locator('ion-split-pane.rail')).toHaveCount(1);
  await expect.poll(async () => (await boxOf(menu)).right, { message: 'the menu folded to the rail' }).toBeLessThanOrEqual(RAIL + 0.5);
  await expect(link).toBeVisible();
  await expect(link.getByText('Upgrade plan')).toBeHidden();
  await expect(link).toHaveAccessibleName('Upgrade plan');
  await expect(link).toHaveAttribute('title', 'Upgrade plan');
  const [at, side] = await Promise.all([boxOf(link), boxOf(menu)]);
  expect(at.left, 'inside the rail').toBeGreaterThanOrEqual(side.left - 0.5);
  expect(at.right, 'inside the rail').toBeLessThanOrEqual(side.right + 0.5);
  expect(await sidewaysOverflow(link), 'the rail\'s «Upgrade plan» fits').toBeLessThanOrEqual(0);
  expect(await sidewaysOverflow(foot), 'the rail\'s foot fits').toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot('APP-BASE-1-BASE-F11-rail-1440') });
  await rail.click();
  await expect(page.locator('ion-split-pane.rail')).toHaveCount(0);
});

/** A ⛔ step pending: what `base.setup.status` says until Invoicing has the business's tax details. */
const IDENTITY_PENDING = {
  total: 1,
  pending: 1,
  unavailable: 0,
  blocking_pending: 1,
  items: [
    {
      key: 'invoice.business_identity',
      app: 'invoice',
      state: 'pending',
      level: 'legal',
      required: true,
      actionable: true,
      title: "Your business's tax details",
      description: 'The name, tax ID and address every invoice carries.',
      icon: 'ion:receipt-outline',
      route: '/invoice/settings',
      order: 10,
    },
  ],
};

/** Answers the page's live stream: `base.setup.status` with the ⛔ step pending, nothing for the other queries. */
async function oneBlockingStep(route: Route): Promise<void> {
  const frames = ['event: hello\ndata: {}\n\n'];
  for (const sub of decodeSubs(route.request().url()) as { id: string; op: string }[]) {
    if (sub.op === 'base.setup.status') {
      frames.push(`event: result\ndata: ${JSON.stringify({ id: sub.id, data: IDENTITY_PENDING, rev: 1 })}\n\n`);
    }
  }
  await route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body: frames.join('') });
}

async function openWithBlockingStep(page: Page, path: string): Promise<void> {
  await page.goto('about:blank');
  await page.route(/\/api\/live\?/, oneBlockingStep);
  await page.goto(`${A}${path}`);
}

test('BASE-F01 — the blocking strip sits between the bar and the content, at its own height', async ({ page }) => {
  await login(page, A, '/');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await openWithBlockingStep(page, '/#actividad');
    const screen = shown(page);
    const strip = screen.locator('[data-testid="blocking-strip"]');
    await expect(strip).toBeVisible();
    await expect(strip).toContainText("Your business's tax details");
    const [bar, notice, body, content] = await Promise.all([
      boxOf(screen.locator(':scope > ion-header')),
      boxOf(screen.locator(':scope > .page-notice')),
      boxOf(strip),
      boxOf(screen.locator(':scope > ion-content')),
    ]);
    expect(notice.top, `under the bar at ${vp.label}`).toBeGreaterThanOrEqual(bar.bottom - 0.5);
    expect(content.top, `the content under the strip at ${vp.label}`).toBeGreaterThanOrEqual(notice.bottom - 0.5);
    expect(body.height, `the strip has a height at ${vp.label}`).toBeGreaterThan(0);
    expect(notice.height, `the strip whole, never squeezed, at ${vp.label}`).toBeGreaterThanOrEqual(body.height - 0.5);
    await page.screenshot({ path: shot(`APP-BASE-1-BASE-F01-strip-${vp.label}`) });
    await page.unroute(/\/api\/live\?/);
  }
});

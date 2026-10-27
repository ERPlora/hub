// BASE-F108 · «Report a problem» from the user menu, without leaving the hub (FIX-HUB-BASE-REPORT-PROBLEM-MODAL), as a
// person sees it at 390, 834 and 1440, against the stack's SaaS with no mocks: the user menu's entry opens the dialog of
// `@erplora/ui` in the hub (no new tab, the address does not move), «Send report» waits for both fields, and the report
// reaches erplora.com, which mails its support mailbox «Reply-To» the account, with «From: Hub» and this business
// (ACCOUNTS-F38), read here from the stack SaaS's mail folder. One report per run: erplora.com allows five an hour per
// account (SUPPORT_REPORT_RATELIMIT), so the other sizes cancel theirs.
// flow: BASE-F108 base-user-menu-report
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { expect, type Page, test } from '@playwright/test';

import { A, login, MAIL_DIR, OWNER, psql, shot, shown, untilStill } from './helpers';

const VIEWPORTS = [
  // A low phone too: the sheet scrolls its fields, and «Send report» stays on screen.
  { label: '375', width: 375, height: 667 },
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** The side menu is pinned from 992 px; below it is a drawer behind the bar's menu button. */
const PINNED_MIN = 992;

/** The Home painted (loaded again unless `reload` is false), then the person at the top of the side menu tapped: its
 *  popover presented. */
async function openUserMenu(page: Page, width: number, reload = true): Promise<void> {
  if (reload) await page.goto(`${A}/`);
  await expect(shown(page).locator('[data-testid="setup-progress"]')).toBeVisible();
  if (width < PINNED_MIN) {
    const opened = page.evaluate(() => new Promise<void>((resolve) => document.addEventListener('ionDidOpen', () => resolve(), { once: true })));
    await shown(page).locator('ion-menu-button').click();
    await opened;
  }
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await page.locator('ion-menu [data-testid="user-menu-trigger"] .sidebar-user-name').click();
  await presented;
}

/** «Report a problem» of the user menu: the dialog presents itself in the hub, never a tab of erplora.com. */
async function openReport(page: Page, width: number, reload = true): Promise<void> {
  await openUserMenu(page, width, reload);
  const popups: Page[] = [];
  page.context().on('page', (opened) => popups.push(opened));
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionModalDidPresent', () => resolve(), { once: true })),
  );
  const entry = page.locator('ion-popover [data-testid="user-menu-report"]');
  await expect(entry).toContainText('Report a problem');
  await expect(entry.locator('a.item-native')).toHaveCount(0);
  await entry.click();
  await presented;
  expect(popups, 'no tab of erplora.com opens').toEqual([]);
  await expect(page).toHaveURL(`${A}/`);
  // The user menu closed before the dialog opened: never under it.
  await expect(page.locator('ion-popover [data-testid="user-menu-report"]')).toBeHidden();
}

const dialog = (page: Page) => page.locator('ion-modal[data-testid="report-problem"]');

async function fill(page: Page, subject: string): Promise<void> {
  await dialog(page).getByTestId('report-problem-subject').locator('input').fill(subject);
  await dialog(page).getByTestId('report-problem-description').locator('textarea').fill('It prints half a ticket and stops.');
}

/** The support mail the stack's SaaS wrote (Django's file backend) since `since` for `subject`, whole. */
function supportMail(subject: string, since: number): string | undefined {
  for (const name of readdirSync(MAIL_DIR)) {
    const path = join(MAIL_DIR, name);
    if (statSync(path).mtimeMs < since - 1000) continue;
    const message = readFileSync(path, 'utf8')
      .split(/^-{79}[ \t]*$/m)
      .find((part) => part.includes(`Subject: [Support] ${subject}`));
    if (message) return message.replace(/=\r?\n/g, '');
  }
  return undefined;
}

test('BASE-F108 — «Report a problem» opens in the hub at every size; «Send report» waits for both fields; «Cancel» sends nothing', async ({ page }) => {
  await login(page, A, '/');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await openReport(page, vp.width);
    const modal = dialog(page);
    // Named by its title: Ionic moves the name into its own dialog, in its shadow root.
    await expect(page.getByRole('dialog', { name: 'Report a problem' })).toBeVisible();
    await expect(modal.getByTestId('report-problem-intro')).toHaveText('Tell us what went wrong. We will reply by email.');
    await expect(modal.getByTestId('report-problem-context')).toHaveText(
      'Your account, your businesses, the page you came from and your browser go with your report.',
    );
    const send = modal.getByTestId('report-problem-submit');
    await expect(send).toHaveText('Send report');
    await expect(send).toHaveAttribute('aria-disabled', 'true');
    await fill(page, `Printer stops ${vp.label}`);
    await expect(send).not.toHaveAttribute('aria-disabled', 'true');
    // The dialog whole inside the screen: a sheet from the bottom on a phone, a centred card from 640 px.
    const box = await modal.locator('.ep-form-modal__content').boundingBox();
    expect(box, `the dialog is painted at ${vp.label}`).not.toBeNull();
    expect(box!.x, `inside on the left at ${vp.label}`).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width, `inside on the right at ${vp.label}`).toBeLessThanOrEqual(vp.width + 0.5);
    await expect(send, `«Send report» on screen at ${vp.label}`).toBeInViewport();
    await untilStill(page);
    await page.screenshot({ path: shot(`FIX-HUB-BASE-REPORT-PROBLEM-MODAL-${vp.label}`) });
    const dismissed = page.evaluate(
      () => new Promise<void>((resolve) => document.addEventListener('ionModalDidDismiss', () => resolve(), { once: true })),
    );
    await modal.getByTestId('report-problem-cancel').click();
    await dismissed;
    await expect(page).toHaveURL(`${A}/`);
  }
});

test('BASE-F108 — the report reaches erplora.com\'s support «Reply-To» the account, with this business, without leaving the hub', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  const subject = `Printer stops ${Date.now()}`;
  const since = Date.now();
  await openReport(page, 1440);
  await fill(page, subject);
  await dialog(page).getByTestId('report-problem-submit').click();
  const sent = dialog(page).getByTestId('report-problem-sent');
  await expect(sent).toContainText('Report sent');
  await expect(sent).toContainText(`will reply to ${OWNER.email} as soon as possible.`);
  await expect(page).toHaveURL(`${A}/`);
  await untilStill(page);
  await page.screenshot({ path: shot('FIX-HUB-BASE-REPORT-PROBLEM-MODAL-sent-1440') });

  await expect.poll(() => supportMail(subject, since) !== undefined, { timeout: 15_000 }).toBe(true);
  const mail = supportMail(subject, since)!;
  const hubId = psql("SELECT id FROM base_hub WHERE slug = 'a'");
  expect(mail).toMatch(new RegExp(`^Reply-To: ${OWNER.email}$`, 'mi'));
  expect(mail).toContain('It prints half a ticket and stops.');
  expect(mail).toContain('From: Hub');
  expect(mail).toContain(`Business: a (${hubId})`);
  expect(mail).toContain('Page: /');

  // «Close» closes it; opened again (the same page, never reloaded), it starts empty.
  const dismissed = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionModalDidDismiss', () => resolve(), { once: true })),
  );
  await dialog(page).getByTestId('report-problem-done').click();
  await dismissed;
  await openReport(page, 1440, false);
  await expect(dialog(page).getByTestId('report-problem-subject').locator('input')).toHaveValue('');
  await expect(dialog(page).getByTestId('report-problem-submit')).toHaveAttribute('aria-disabled', 'true');
});

// flow: BASE-F05 (base/WORKBOOK.md, «Abrir una app desde «Mis apps»», «Si falla»; gh:hub#438)
// After a deploy the open tab still knows the old names of the screens' files, and the new image no longer serves
// them: a tap on a screen not opened yet in that tab did nothing and said nothing until the app was restarted. Here
// the server stops serving one screen's file once, as after a deploy, and the tap must open it anyway, in a fresh
// document (which names the new files); offline, the screen the person is on stays and a toast says so, with «Retry».
import { mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, capture, login, shown } from './helpers';

/** Where the fleet keeps the evidence of this change (`## UI vista` of its PR), outside the repo. */
const EVIDENCE = process.env.E2E_EVIDENCE_DIR ?? join(homedir(), '.erplora', 'fleet-next', 'logs', '438', 'ui');

/** `capture` (still and painted, in `.artifacts/`), and a copy of it among the evidence. */
async function evidence(page: Page, name: string): Promise<void> {
  const png = await capture(page, name);
  mkdirSync(EVIDENCE, { recursive: true });
  writeFileSync(join(EVIDENCE, `${name}.png`), png);
}

const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

/** A screen's file as Vite serves it (dev) or as the build names it (`<Page>-<hash>.js`). */
const fileOf = (page: string): RegExp => new RegExp(`/${page}(\\.vue|-[\\w-]+\\.js)(\\?.*)?$`);

/** The next request for `file` gets the 404 of a file the new image no longer has; the ones after it, the file. */
async function goneOnce(page: Page, file: RegExp): Promise<() => number> {
  let refused = 0;
  await page.route(file, async (route) => {
    if (refused > 0) return route.fallback();
    refused += 1;
    return route.fulfill({ status: 404, contentType: 'text/plain', body: 'Not Found' });
  });
  return () => refused;
}

/** Home, signed in, with a mark on the document: a fresh document no longer has it. */
async function homeOf(browser: Browser, size: (typeof SIZES)[number]) {
  const context = await browser.newContext({ locale: 'en-US', viewport: size });
  const page = await context.newPage();
  await login(page, A, '/');
  await expect(shown(page).getByTestId('home-my-apps-add')).toBeVisible();
  await page.evaluate(() => ((window as unknown as { tabBeforeTheTap?: true }).tabBeforeTheTap = true));
  return { context, page };
}

const sameDocument = (page: Page) =>
  page.evaluate(() => (window as unknown as { tabBeforeTheTap?: true }).tabBeforeTheTap === true);

test('BASE-F05 · gh:hub#438: after a deploy, «Add apps» on Home opens Apps in a fresh document instead of doing nothing', async ({
  browser,
}) => {
  const { context, page } = await homeOf(browser, SIZES[0]);
  try {
    const refused = await goneOnce(page, fileOf('AppsPage'));
    await shown(page).getByTestId('home-my-apps-add').click();
    await expect(page).toHaveURL(`${A}/apps`);
    await expect(shown(page).getByTestId('apps-counter')).toBeVisible();
    expect(refused()).toBe(1);
    expect(await sameDocument(page)).toBe(false);
  } finally {
    await context.close();
  }
});

test('BASE-F05 · gh:hub#438: after a deploy, «Employees» in the side menu opens in a fresh document instead of doing nothing', async ({
  browser,
}) => {
  const { context, page } = await homeOf(browser, SIZES[0]);
  try {
    const refused = await goneOnce(page, fileOf('EmployeesPage'));
    await page.getByTestId('nav-employees').click();
    await expect(page).toHaveURL(`${A}/employees`);
    await expect(shown(page).getByRole('heading', { name: 'Employees' }).first()).toBeVisible();
    expect(refused()).toBe(1);
    expect(await sameDocument(page)).toBe(false);
  } finally {
    await context.close();
  }
});

for (const size of SIZES) {
  test(`BASE-F05 · gh:hub#438: offline, a screen that cannot load keeps Home and says so, and «Retry» opens it, at ${size.width}x${size.height}`, async ({
    browser,
  }) => {
    const { context, page } = await homeOf(browser, size);
    try {
      await context.setOffline(true);
      await shown(page).getByTestId('home-my-apps-add').click();
      const notice = page.locator('ion-toast#view-load-failed');
      await expect(notice).toBeVisible();
      await expect(notice).toContainText('Could not open that page. Check the connection and try again.');
      await expect(page).toHaveURL(`${A}/`);
      await expect(shown(page).getByTestId('home-my-apps-add')).toBeVisible();
      await evidence(page, `1-home-offline-toast-${size.width}x${size.height}`);

      await context.setOffline(false);
      await notice.getByRole('button', { name: 'Retry' }).click();
      await expect(page).toHaveURL(`${A}/apps`);
      await expect(shown(page).getByTestId('apps-counter')).toBeVisible();
      expect(await sameDocument(page)).toBe(false);
      await evidence(page, `2-apps-after-retry-${size.width}x${size.height}`);
    } finally {
      await context.close();
    }
  });
}

// flow: BASE-F48 (base/WORKBOOK.md)
// Settings offers each person only the tabs they can use. In `a`, the employee has «General» and «Business»: a saved
// link to «Data and backups» or «Printing» opens «General» and paints nothing of the other. The owner has the four.
// The employee's page at the three sizes, captured.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, capture, type Credentials, EMPLOYEE, hostPage, OWNER, shown, THREE_SIZES, untilStill } from './helpers';

async function signedIn(browser: Browser, credentials: Credentials, next: string) {
  return hostPage(browser, A, { next, credentials });
}

/** The tabs Settings offers, by their ids. */
async function tabIds(page: Page): Promise<string[]> {
  const tabs = shown(page).locator('ion-segment-button[data-testid^="tab-"]');
  await expect(tabs.first()).toBeVisible();
  return tabs.evaluateAll((buttons) => buttons.map((button) => button.getAttribute('data-testid') ?? ''));
}

test('an employee has «General» and «Business», and a link to the others opens «General»', async ({ browser }) => {
  const { context, page } = await signedIn(browser, EMPLOYEE, '/settings#data');
  for (const { label, width, height } of THREE_SIZES) {
    await page.setViewportSize({ width, height });
    for (const hash of ['#data', '#tickets']) {
      // A whole page load each time, as a saved link opens: a goto that only changes the hash would not load it again.
      await page.goto('about:blank');
      await page.goto(`/settings${hash}`);
      await expect.poll(() => tabIds(page), `${hash} at ${label}`).toEqual(['tab-general', 'tab-business']);
      await expect(shown(page).getByTestId('tab-general')).toHaveClass(/segment-button-checked/);
      await expect(shown(page).getByTestId('device-mode-card')).toBeVisible();
      await expect(shown(page).getByTestId('data-sections')).toHaveCount(0);
      await expect(shown(page).getByTestId('tickets-printers')).toHaveCount(0);
    }
    await untilStill(page);
    await capture(page, `BASE-F48-settings-employee-${label}`, { fullPage: true });
  }
  await context.close();
});

test('the owner has the four tabs of Settings', async ({ browser }) => {
  const { context, page } = await signedIn(browser, OWNER, '/settings#data');
  await expect.poll(() => tabIds(page)).toEqual(['tab-general', 'tab-business', 'tab-tickets', 'tab-data']);
  await expect(shown(page).getByTestId('data-sections')).toBeVisible();
  await context.close();
});

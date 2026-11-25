// flow: BASE-F126 (base/WORKBOOK.md)
// «Support access» closes Settings › General of `a`. The owner turns it on (a notice says what it allows and the card
// says who changed it), sees who of support came in and when, and turns it off again; an employee reads it with the
// switch disabled. Support comes in from erplora.com, so the test writes its entry in the business's database, as that
// entry leaves it. Each state at the three sizes; afterwards the business has it as it came: off and with no entries.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, EMPLOYEE, hostPage, login, psql, shown, THREE_SIZES } from './helpers';

const CARD = '[data-testid="support-access-card"]';
const TOGGLE = '[data-testid="support-access-toggle"]';
const VISITOR = 'Sara Soto';

function forgetSupportAccess(): void {
  psql('delete from base_supportvisit; delete from base_supportaccess');
}

test.describe.configure({ mode: 'serial' });
test.beforeAll(forgetSupportAccess);
test.afterAll(forgetSupportAccess);

const card = (page: Page): Locator => shown(page).locator(CARD);
const toast = (page: Page, text: string): Locator => page.getByTestId('toast').filter({ hasText: text }).first();

async function captureAtEachSize(page: Page, name: string): Promise<void> {
  for (const { label, width, height } of THREE_SIZES) {
    await page.setViewportSize({ width, height });
    await card(page).scrollIntoViewIfNeeded();
    await expect(card(page).locator(TOGGLE)).toBeInViewport();
    await capture(page, `BASE-F126-${name}-${label}`);
  }
}

test('the owner turns support access on, sees who of support came in, and turns it off', async ({ page }) => {
  await login(page, A, '/settings');
  await expect(card(page).locator(TOGGLE)).toHaveJSProperty('checked', false);
  await expect(card(page).locator(TOGGLE)).toHaveJSProperty('disabled', false);
  await expect(card(page).getByTestId('support-visits-empty')).toHaveText('Nobody from ERPlora support has come in yet.');
  await expect(card(page).getByTestId('support-access-changed')).toHaveCount(0);
  await captureAtEachSize(page, 'off');

  await card(page).locator(TOGGLE).click();
  await expect(toast(page, 'Support access is on: ERPlora support can come in.')).toBeVisible();
  await expect(card(page).locator(TOGGLE)).toHaveJSProperty('checked', true);
  await expect(card(page).getByTestId('support-access-changed')).toContainText('Last changed by');
  expect(psql('select enabled from base_supportaccess')).toBe('t');

  psql(
    'insert into base_supportvisit (id, username, name, email, entered_at) ' +
      `values (gen_random_uuid(), 'saas-support:e2e', '${VISITOR}', '', now())`,
  );
  await page.reload();
  await expect(card(page).getByTestId('support-visit')).toHaveCount(1);
  await expect(card(page).getByTestId('support-visit')).toContainText(VISITOR);
  await expect(card(page).getByTestId('support-visits-empty')).toHaveCount(0);
  await captureAtEachSize(page, 'on');

  await card(page).locator(TOGGLE).click();
  await expect(toast(page, 'Support access is off: ERPlora support can no longer come in.')).toBeVisible();
  await expect(card(page).locator(TOGGLE)).toHaveJSProperty('checked', false);
  expect(psql('select enabled from base_supportaccess')).toBe('f');
});

test('an employee reads it with the switch disabled, and why', async ({ browser }) => {
  const { context, page } = await hostPage(browser, A, { next: '/settings', credentials: EMPLOYEE });
  await expect(card(page).locator(TOGGLE)).toHaveJSProperty('disabled', true);
  await expect(card(page)).toContainText('Only who runs the business can change it.');
  await captureAtEachSize(page, 'employee');
  await context.close();
});

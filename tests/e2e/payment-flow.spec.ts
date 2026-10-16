// Payments in Chrome (WORKBOOK PAYMENT-F01 to F08), hidden by default: the owner creates the account it
// pays from in Methods (a repeated name is refused under Name), records a payment with the amount typed
// as a person does, takes it up the ladder by each row's own action (Approve, Mark as sent, Mark as
// completed), cancels a second one with its reason, finds a payment by a piece of its reference, and
// deactivates the method, which then leaves «New payment». An employee only looks. Each screen is
// captured in three viewports. Everything this spec creates is named «E2E Pay …» and removed before
// and after it.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, login, psql, shot, shown } from './helpers';

const TAG = 'E2E Pay';
const named = (label: string): string => `${TAG} ${label} ${Date.now().toString(36)}`;
const VIEWPORTS = {
  desktop: { width: 1280, height: 860 },
  tablet: { width: 820, height: 1180 },
  phone: { width: 390, height: 844 },
} as const;

/** Deletes what the spec created; the counter of the day goes too when no payment of the day is left. */
function cleanUp(): void {
  const methods = `select id from payment_paymentmethod where name like '${TAG}%'`;
  psql(
    [
      `delete from payment_payment where method_id in (${methods}) or beneficiary_name like '${TAG}%'`,
      `delete from payment_paymentmethod where name like '${TAG}%'`,
      `delete from payment_paymentcounter c where not exists (select 1 from payment_payment p where p.reference like 'PAY-' || to_char(c.day, 'YYYYMMDD') || '-%')`,
    ].join('; '),
  );
}

async function pageAs(browser: Browser, next: string, viewport: { width: number; height: number } = VIEWPORTS.desktop, employee = false) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, employee ? EMPLOYEE : undefined);
  return { context, page };
}

/** Runs a row action: its button, or the same entry inside «⋮» when the row folds its actions. */
async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  const menu = shown(page).locator(`[data-testid=${table}-row-${id}-menu]`);
  await button.or(menu).first().waitFor({ state: 'visible' });
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await menu.click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

/** Picks `text` in the ion-select `testid` (a popover). */
async function choose(page: Page, testid: string, text: string): Promise<void> {
  await page.locator(`[data-testid=${testid}]`).click();
  const option = page.locator('ion-popover').getByText(text, { exact: true });
  await option.click();
  await expect(option).toBeHidden();
}

const rowOf = (page: Page, table: string, id: string) => shown(page).locator(`[data-testid=${table}-row][data-id="${id}"]`).first();

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('Methods and payments: create, refuse a twin, the whole ladder, cancel with a reason, search, deactivate', async ({ browser }) => {
  const bank = named('Bank');
  const supplier = named('Proveedor');
  const other = named('Lavandería');
  const { context, page } = await pageAs(browser, '/payment/methods');
  try {
    // Methods: create one; the same name in another case is refused under Name (409).
    let view = shown(page);
    await view.locator('[data-testid=payment-methods-empty], [data-testid=payment-methods-row]').first().waitFor({ state: 'visible' });
    await view.locator('[data-testid=payment-methods-add]').click();
    await page.locator('[data-testid=payment-method-form-name] input').fill(bank);
    await page.locator('[data-testid=payment-method-form-account] input').fill('*1332');
    await page.locator('[data-testid=payment-method-form-submit]').click();
    const methodRow = view.locator('[data-testid=payment-methods-row]', { hasText: bank }).first();
    await expect(methodRow).toContainText('Bank transfer');
    await expect(methodRow).toContainText('Active');
    await view.locator('[data-testid=payment-methods-add]').click();
    await page.locator('[data-testid=payment-method-form-name] input').fill(bank.toUpperCase());
    await page.locator('[data-testid=payment-method-form-submit]').click();
    await expect(page.locator('[data-testid=payment-method-form]')).toContainText(
      'There is already a payment method with that name. Pick another name.',
    );
    await page.locator('[data-testid=payment-method-form-cancel]').click();
    const methodId = psql(`select id from payment_paymentmethod where name = '${bank}'`);

    // Payments: «New payment» with the method, the amount as typed, the beneficiary.
    await page.goto(`${A}/payment/payments`);
    view = shown(page);
    await view.locator('[data-testid=payment-payments-empty], [data-testid=payment-payments-row]').first().waitFor({ state: 'visible' });
    await view.locator('[data-testid=payment-payments-add]').click();
    await choose(page, 'payment-form-method', bank);
    await page.locator('[data-testid=payment-form-amount] input').fill('1,250.50');
    await page.locator('[data-testid=payment-form-beneficiary] input').fill(supplier);
    await page.locator('[data-testid=payment-form-concept] input').fill('Tintes de octubre');
    await page.screenshot({ path: shot('payment-new-desktop'), animations: 'disabled' });
    await page.locator('[data-testid=payment-form-submit]').click();
    await expect.poll(() => psql(`select count(*) from payment_payment where beneficiary_name = '${supplier}'`)).toBe('1');
    const paymentId = psql(`select id from payment_payment where beneficiary_name = '${supplier}'`);
    const reference = psql(`select reference from payment_payment where id = '${paymentId}'`);
    expect(reference).toMatch(/^PAY-\d{8}-\d{4,}$/);
    const row = rowOf(page, 'payment-payments', paymentId);
    await expect(row).toContainText(reference);
    await expect(row).toContainText('€1,250.50');
    await expect(row).toContainText('Draft');

    // The ladder, each step by the row's own action.
    for (const [label, status] of [
      ['Approve', 'Approved'],
      ['Mark as sent', 'Sent'],
      ['Mark as completed', 'Completed'],
    ] as const) {
      await expect(view.locator(`[data-testid=payment-payments-row-${paymentId}-advance]`).first()).toContainText(label);
      await rowAction(page, 'payment-payments', paymentId, 'advance');
      await expect(row).toContainText(status);
    }
    await expect(view.locator(`[data-testid=payment-payments-row-${paymentId}-advance]:visible`)).toHaveCount(0);
    expect(psql(`select status from payment_payment where id = '${paymentId}'`)).toBe('completed');

    // A second payment, cancelled with its reason.
    await view.locator('[data-testid=payment-payments-add]').click();
    await choose(page, 'payment-form-method', bank);
    await page.locator('[data-testid=payment-form-amount] input').fill('40');
    await page.locator('[data-testid=payment-form-beneficiary] input').fill(other);
    await page.locator('[data-testid=payment-form-submit]').click();
    await expect.poll(() => psql(`select count(*) from payment_payment where beneficiary_name = '${other}'`)).toBe('1');
    const otherId = psql(`select id from payment_payment where beneficiary_name = '${other}'`);
    await rowAction(page, 'payment-payments', otherId, 'cancel');
    await expect(page.locator('[data-testid=payment-cancel-submit]')).toHaveAttribute('aria-disabled', 'true');
    await page.locator('[data-testid=payment-cancel-reason] textarea').fill('Duplicated');
    await page.locator('[data-testid=payment-cancel-submit]').click();
    const otherRow = rowOf(page, 'payment-payments', otherId);
    await expect(otherRow).toContainText('Cancelled');
    await expect(otherRow).toContainText('Reason: Duplicated');

    // A piece of the reference finds the payment.
    await view.locator('[data-testid=payment-payments-search] input').fill(reference.slice(-4));
    await expect(row).toBeVisible();
    await expect(view.locator('[data-testid=payment-payments-row]', { hasText: other })).toHaveCount(0);
    await page.screenshot({ path: shot('payment-payments-desktop') });

    // Deactivating the method takes it out of «New payment».
    await page.goto(`${A}/payment/methods`);
    view = shown(page);
    await rowAction(page, 'payment-methods', methodId, 'deactivate');
    await expect(rowOf(page, 'payment-methods', methodId)).toContainText('Deactivated');
    await page.screenshot({ path: shot('payment-methods-desktop') });
    await page.goto(`${A}/payment/payments`);
    view = shown(page);
    await view.locator('[data-testid=payment-payments-add]').click();
    const picker = page.locator('[data-testid=payment-form-method]');
    await expect(picker.locator('ion-select-option', { hasText: bank })).toHaveCount(0);
    await page.locator('[data-testid=payment-form-cancel]').click();
  } finally {
    await context.close();
  }
});

test('The three viewports of both screens', async ({ browser }) => {
  for (const [name, viewport] of Object.entries(VIEWPORTS)) {
    const { context, page } = await pageAs(browser, '/payment/payments', viewport);
    try {
      let view = shown(page);
      await view.locator('[data-testid=payment-payments-empty], [data-testid=payment-payments-row]').first().waitFor({ state: 'visible' });
      await expect(view.locator('[data-testid=payment-payments-add]')).toBeVisible();
      await page.screenshot({ path: shot(`payment-payments-${name}`) });
      await page.goto(`${A}/payment/methods`);
      view = shown(page);
      await view.locator('[data-testid=payment-methods-empty], [data-testid=payment-methods-row]').first().waitFor({ state: 'visible' });
      await page.screenshot({ path: shot(`payment-methods-${name}`) });
    } finally {
      await context.close();
    }
  }
});

test('An employee only looks: no New payment, no New method, no row action', async ({ browser }) => {
  const { context, page } = await pageAs(browser, '/payment/payments', VIEWPORTS.desktop, true);
  try {
    const view = shown(page);
    await view.locator('[data-testid=payment-payments-empty], [data-testid=payment-payments-row]').first().waitFor({ state: 'visible' });
    await expect(view.locator('[data-testid=payment-payments-add]')).toHaveCount(0);
    await expect(view.locator('[data-testid$=-advance]:visible, [data-testid$=-cancel]:visible')).toHaveCount(0);
    await page.goto(`${A}/payment/methods`);
    const methods = shown(page);
    await methods.locator('[data-testid=payment-methods-empty], [data-testid=payment-methods-row]').first().waitFor({ state: 'visible' });
    await expect(methods.locator('[data-testid=payment-methods-add]')).toHaveCount(0);
    await page.screenshot({ path: shot('payment-employee') });
  } finally {
    await context.close();
  }
});

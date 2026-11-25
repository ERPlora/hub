// The two dates of a manual invoice in Chrome (apps/invoice/WORKBOOK.md): INVOICE-F03, an invoice of yesterday that fell
// due yesterday too, and a day before the last invoice of its series refused under the field; INVOICE-F16, it reads
// «Overdue» and the list keeps the overdue ones; INVOICE-F17 and F19, its due date on its page and «Paid» once paid.
// The invoices go in a series of the run's own, so the ones of today in FACT never stop it. What it creates is deleted.
import { expect, type Page, test } from '@playwright/test';

import { madridToday, shifted } from './assistant-setup';
import { dayAsShown, pickDay } from './date-time-fields';
import { A, api, login, shown } from './helpers';
import { cleanInvoices, flowShots, issuedIds, openDialog, readyToInvoice } from './invoice-helpers';
import { stamp } from './sale-helpers';
import { choose } from './task-helpers';

const RUN = stamp();
const SERIES = `E2E-${RUN}`.toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 20);
const TODAY = madridToday(new Date());
const YESTERDAY = shifted(TODAY, -1);
const BEFORE = shifted(TODAY, -2);

test.beforeAll(async ({ browser }) => {
  const context = await readyToInvoice(browser);
  const series = await api(context, A, 'POST', '/invoice/series', { code: SERIES, invoice_type: 'F2', year: Number(YESTERDAY.slice(0, 4)), name: 'e2e dates' });
  expect(series.status, JSON.stringify(series.data)).toBe(201);
  await context.close();
});

test.afterAll(() => cleanInvoices());

/** «New manual invoice» open in the run's series, with one line. */
async function newInvoice(page: Page, customer: string) {
  await shown(page).locator('[data-testid=invoice-list-add]').click();
  const dialog = openDialog(page, 'invoice-create');
  await expect(dialog).toBeVisible();
  await choose(page, dialog.locator('[data-testid=invoice-create-series]'), `${SERIES} — e2e dates \\(F2\\)`);
  await dialog.locator('[data-testid=invoice-recipient-name] input').fill(customer);
  await dialog.locator('[data-testid=invoice-line-1-description] input').fill(`e2e Consulting ${RUN}`);
  await dialog.locator('[data-testid=invoice-line-1-price] input').fill('50');
  return dialog;
}

test('INVOICE-F03, F16, F17 and F19: an invoice of yesterday that fell due is overdue until it is paid', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  const customer = `e2e Vencida ${RUN}`;
  const dialog = await newInvoice(page, customer);
  const issued = dialog.locator('[data-testid=invoice-create-issue-date]');
  const due = dialog.locator('[data-testid=invoice-create-due-date]');
  await expect(issued.locator('input')).toHaveValue(dayAsShown(TODAY));
  await expect(due.locator('input')).toHaveValue('');
  await pickDay(page, issued, YESTERDAY);
  await pickDay(page, due, YESTERDAY);
  await expect(issued.locator('input')).toHaveValue(dayAsShown(YESTERDAY));
  await flowShots(page, 'INVOICE-F03-dates', async (p) => {
    await expect(openDialog(p, 'invoice-create').locator('[data-testid=invoice-create-due-date]')).toBeVisible();
  });
  await dialog.locator('[data-testid=invoice-create-submit]').click();
  await expect(dialog).toBeHidden();

  // The list says so by itself, and keeps it among the overdue ones.
  const row = shown(page).locator('[data-testid=invoice-list-row]', { hasText: customer });
  await expect(row.locator('[data-testid=invoice-list-status]')).toHaveText('Overdue');
  await shown(page).locator('[data-testid=invoice-list-filters-toggle]').click();
  const panel = shown(page).locator('[data-testid=invoice-list-filters-panel]');
  await choose(page, panel.locator('[data-testid=invoice-list-filter-status]'), 'Overdue');
  await panel.locator('[data-testid=invoice-list-filters-apply]').click();
  await expect(panel).toBeHidden();
  await expect(row).toBeVisible();
  await expect(shown(page).locator('[data-testid=invoice-list-status]').filter({ hasNotText: 'Overdue' })).toHaveCount(0);
  await flowShots(page, 'INVOICE-F16-overdue', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-list-row]', { hasText: customer }).locator('[data-testid=invoice-list-status]')).toBeVisible();
  });

  await row.click();
  await page.waitForURL(/\/invoice\/invoices\/[0-9a-f-]+$/);
  issuedIds.add(page.url().split('/').at(-1)!);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-issue-date]')).toHaveText(new Intl.DateTimeFormat('en', { timeZone: 'UTC' }).format(Date.parse(YESTERDAY)));
  await expect(detail.locator('[data-testid=invoice-detail-due-date]')).toHaveText(new Intl.DateTimeFormat('en', { timeZone: 'UTC' }).format(Date.parse(YESTERDAY)));
  await expect(detail.locator('[data-testid=invoice-detail-operation-date]')).toHaveCount(0);
  await expect(detail.locator('[data-testid=invoice-detail-status]')).toHaveText('Overdue');
  await flowShots(page, 'INVOICE-F17-overdue', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-detail-due-date]')).toBeVisible();
  });
  await detail.locator('[data-testid=invoice-detail-mark-paid]').click();
  const confirm = page.locator('ion-modal').filter({ hasText: 'as paid?' }).last();
  await confirm.locator('.ep-form-modal__submit').click();
  await expect(confirm).toBeHidden();
  await expect(detail.locator('[data-testid=invoice-detail-status]')).toHaveText('Paid');
  await expect(detail.locator('[data-testid=invoice-detail-due-date]')).toBeVisible();
  await page.goto(`${A}/invoice/invoices`);
  await expect(shown(page).locator('[data-testid=invoice-list-row]', { hasText: customer }).locator('[data-testid=invoice-list-status]')).toHaveText('Paid');

  // One of the day before would go before the last of its series: said under the field, and nothing is issued.
  const second = await newInvoice(page, `e2e Antes ${RUN}`);
  const again = second.locator('[data-testid=invoice-create-issue-date]');
  await pickDay(page, again, BEFORE);
  await second.locator('[data-testid=invoice-create-submit]').click();
  await expect(again.locator('.error-text')).toContainText('An invoice cannot be dated before the last one of its series');
  await flowShots(page, 'INVOICE-F03-date-refused', async (p) => {
    await expect(openDialog(p, 'invoice-create').locator('[data-testid=invoice-create-issue-date] .error-text')).toBeVisible();
  });
  await pickDay(page, again, YESTERDAY);
  await expect(again.locator('.error-text')).toBeHidden();
  await second.locator('[data-testid=invoice-create-submit]').click();
  await expect(second).toBeHidden();
  await expect(shown(page).locator('[data-testid=invoice-list-row]', { hasText: `e2e Antes ${RUN}` }).locator('[data-testid=invoice-list-status]')).toHaveText('Issued');
});

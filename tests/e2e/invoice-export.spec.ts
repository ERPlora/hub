// «Download in Excel» of Invoices (INVOICE-F24) in Chrome: an invoice with two rates, found by its customer, downloads
// as a real spreadsheet, opened here with a reader of its own: its figures are numbers that add up to what the list
// shows. An employee has no button.
import { readFileSync } from 'node:fs';

import { expect, type Page, test } from '@playwright/test';
import readXlsxFile from 'read-excel-file/node';

import { A, EMPLOYEE, login, shown } from './helpers';
import { cleanInvoices, flowShots, issueByHand, readyToInvoice } from './invoice-helpers';
import { stamp } from './sale-helpers';

const CUSTOMER = `e2e Export ${stamp()}`;
const RECIPIENT = { customer_name: CUSTOMER, customer_tax_id: 'B12345674', customer_address: 'Calle Luna 3' };
const LINES = [
  { description: 'Curso', quantity: '1', unit_price: 10000, tax_rate: '21' },
  { description: 'Manual', quantity: '1', unit_price: 5000, tax_rate: '10' },
];

test.beforeAll(async ({ browser }) => {
  const context = await readyToInvoice(browser);
  await issueByHand(context, { ...RECIPIENT, lines: LINES });
  await context.close();
});

test.afterAll(() => cleanInvoices());

async function searchFor(page: Page, text: string): Promise<void> {
  await page.goto(`${A}/invoice/invoices`);
  await shown(page).locator('[data-testid=invoice-list-search] input').fill(text);
  await expect(shown(page).locator('[data-testid=invoice-list-row]')).toHaveCount(1);
}

test('«Download in Excel» saves the list as a real spreadsheet whose figures add up', async ({ page }) => {
  await login(page, A, '/invoice/invoices');
  await searchFor(page, CUSTOMER);

  const download = page.waitForEvent('download');
  await shown(page).locator('[data-testid=invoice-export]').click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('invoices.xlsx');
  const [{ data }] = await readXlsxFile(readFileSync((await file.path()) as string));
  const [headers, ...rows] = data;

  expect(headers).toHaveLength(8);
  expect(rows).toHaveLength(2);
  const [big, small] = rows;
  expect(big.slice(4)).toEqual([100, 21, 21, 121]);
  expect(small.slice(4)).toEqual([50, 10, 5, 55]);
  expect([big[0], big[2], big[3]]).toEqual([small[0], CUSTOMER, 'B12345674']);
  expect(big[1]).toBeInstanceOf(Date);

  await flowShots(page, 'F24', async (shot) => {
    await expect(shown(shot).locator('[data-testid=invoice-export]')).toBeVisible();
  });
});

test('an employee has no «Download in Excel»', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices', EMPLOYEE);
  await expect(shown(page).locator('[data-testid=invoice-list-row], [data-testid=invoice-list-empty]').first()).toBeVisible();
  await expect(shown(page).locator('[data-testid=invoice-export]')).toHaveCount(0);
  await context.close();
});

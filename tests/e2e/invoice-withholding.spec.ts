// The IRPF withholding of a manual invoice in Chrome (apps/invoice/WORKBOOK.md): INVOICE-F03, 100 € + 21 % with 15 %
// withheld; INVOICE-F17 and F18, its page and its A4 say the total, what is withheld and what is left to collect;
// INVOICE-F08, its rectifying invoice gives it back; INVOICE-F24, the Excel says so too; a ticket is not asked for it.
// What it creates is deleted.
import { readFileSync } from 'node:fs';

import { expect, type Page, test } from '@playwright/test';
import readXlsxFile from 'read-excel-file/node';

import { A, api, login, shown } from './helpers';
import { cleanInvoices, flowShots, invoiceOf, issuedIds, openDialog, readyToInvoice } from './invoice-helpers';
import { stamp } from './sale-helpers';
import { choose } from './task-helpers';

const RUN = stamp();
const CUSTOMER = `e2e Retenida ${RUN}`;

test.beforeAll(async ({ browser }) => (await readyToInvoice(browser)).close());

test.afterAll(() => cleanInvoices());

/** What the open invoice says after its breakdown. */
async function totals(page: Page): Promise<string[]> {
  const texts = ['total', 'withholding', 'payable'].map((part) => shown(page).locator(`[data-testid=invoice-detail-${part}]`).textContent());
  return (await Promise.all(texts)).map((text) => (text ?? '').replace(/\s/g, ' ').trim());
}

test('INVOICE-F03, F17, F18, F08 and F24: an invoice with 15 % withheld says what is left to collect', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  await shown(page).locator('[data-testid=invoice-list-add]').click();
  const dialog = openDialog(page, 'invoice-create');
  const series = dialog.locator('[data-testid=invoice-create-series]');
  await choose(page, series, 'TICKET — .*');
  await expect(dialog.locator('[data-testid=invoice-create-withholding]')).toHaveCount(0);
  await choose(page, series, 'FACT — .*');
  await dialog.locator('[data-testid=invoice-recipient-name] input').fill(CUSTOMER);
  await dialog.locator('[data-testid=invoice-recipient-tax-id] input').fill('B12345674');
  await dialog.locator('[data-testid=invoice-recipient-address] input').fill('Calle Luna 3');
  await dialog.locator('[data-testid=invoice-line-1-description] input').fill(`e2e Consulting ${RUN}`);
  await dialog.locator('[data-testid=invoice-line-1-price] input').fill('100');
  await dialog.locator('[data-testid=invoice-line-1-tax-rate] input').fill('21');
  await choose(page, dialog.locator('[data-testid=invoice-create-withholding]'), '15%');
  await flowShots(page, 'INVOICE-F03-withholding', async (p) => {
    await openDialog(p, 'invoice-create').locator('[data-testid=invoice-create-withholding]').scrollIntoViewIfNeeded();
    await expect(openDialog(p, 'invoice-create').locator('[data-testid=invoice-create-withholding]')).toBeVisible();
  });
  await dialog.locator('[data-testid=invoice-create-submit]').click();
  await expect(dialog).toBeHidden();

  // The list shows the invoice's total, as ever.
  const row = shown(page).locator('[data-testid=invoice-list-row]', { hasText: CUSTOMER });
  await expect(row).toContainText('€121.00');
  await row.click();
  await page.waitForURL(/\/invoice\/invoices\/[0-9a-f-]+$/);
  const id = page.url().split('/').at(-1)!;
  issuedIds.add(id);
  await expect(shown(page).locator('[data-testid=invoice-detail-payable]')).toBeVisible();
  expect(await totals(page)).toEqual(['Total: €121.00', 'IRPF withholding 15%: -€15.00', 'Amount due: €106.00']);
  await flowShots(page, 'INVOICE-F17-withholding', async (p) => {
    await shown(p).locator('[data-testid=invoice-detail-payable]').scrollIntoViewIfNeeded();
    await expect(shown(p).locator('[data-testid=invoice-detail-payable]')).toBeVisible();
  });
  const cells = await page.locator('[data-testid=invoice-paper-taxes]').last().locator('td').allTextContents();
  expect(cells.slice(-6).map((text) => text.replace(/\s/g, ' ').trim())).toEqual([
    'TOTAL',
    '€121.00',
    'IRPF withholding 15%',
    '-€15.00',
    'Amount due',
    '€106.00',
  ]);

  // The server's A4 says the same, and the invoice itself is the one of 121.00 €.
  const { number } = await invoiceOf(page.context(), id);
  const html = (await api<{ html: string }>(page.context(), A, 'GET', `/invoice/invoices/document?invoice_id=${id}`)).data.html;
  expect(html).toContain('<td class="muted">IRPF withholding 15%</td><td class="num">-€15.00</td>');
  expect(html).toContain('<td>Amount due</td><td class="num">€106.00</td>');

  await page.goto(`${A}/invoice/invoices`);
  await shown(page).locator('[data-testid=invoice-list-search] input').fill(CUSTOMER);
  await expect(shown(page).locator('[data-testid=invoice-list-row]')).toHaveCount(1);
  const download = page.waitForEvent('download');
  await shown(page).locator('[data-testid=invoice-export]').click();
  const [{ data }] = await readXlsxFile(readFileSync((await (await download).path()) as string));
  expect(data.map((cells) => cells.slice(7))).toEqual([
    ['Total', 'Withholding %', 'Withholding', 'Amount due'],
    [121, 15, -15, 106],
  ]);

  // Its rectifying invoice gives back what was withheld.
  const rectified = await api<{ invoice: { id: string } }>(page.context(), A, 'POST', '/invoice/invoices/rectify', { number, reason: 'e2e' });
  expect(rectified.status, JSON.stringify(rectified.data)).toBeLessThan(300);
  issuedIds.add(rectified.data.invoice.id);
  await page.goto(`${A}/invoice/invoices/${rectified.data.invoice.id}`);
  await expect(shown(page).locator('[data-testid=invoice-detail-payable]')).toBeVisible();
  expect(await totals(page)).toEqual(['Total: -€121.00', 'IRPF withholding 15%: €15.00', 'Amount due: -€106.00']);
});

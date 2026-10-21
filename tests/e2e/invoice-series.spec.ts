// Invoicing's numbering series in Chrome (apps/invoice/WORKBOOK.md):
//   - INVOICE-F12: the owner creates a series that continues another system's numbering (next number 7);
//   - INVOICE-F13: edits its name; once it has numbered an invoice, prefix, format and next number are
//     locked (the page says why, the server refuses them with 409).
// What this file creates is deleted after it, and the hub's numbering is left as found.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, shown } from './helpers';
import { cleanInvoices, openDialog, ensureIssuer, flowShots, issuedIds, snapshotSeries } from './invoice-helpers';
import { stamp } from './sale-helpers';

const RUN = stamp();
const CODE = `E2E${RUN}`.slice(0, 20);
const PREFIX = 'E2EW';
let year: number;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/invoice/series');
  snapshotSeries();
  await ensureIssuer(context);
  year = (await api<{ fiscal_year: number }>(context, A, 'GET', '/invoice/numbering/status')).data.fiscal_year;
  await context.close();
});

test.afterAll(() => {
  cleanInvoices();
});

interface SeriesOut {
  id: string;
  code: string;
  name: string;
  current_number: number;
  next_number: string;
  format_locked: boolean;
}

async function seriesOf(page: Page): Promise<SeriesOut> {
  const res = await api<{ rows: SeriesOut[] }>(page.context(), A, 'GET', `/invoice/series?code=${CODE}&limit=10`);
  expect(res.data.rows, `series ${CODE}`).toHaveLength(1);
  return res.data.rows[0];
}

const rowOf = (page: Page) => shown(page).locator('[data-testid=invoice-series-row]', { hasText: CODE }).first();

test('INVOICE-F12 and F13: a series that continues at 7, renamed, and locked once it numbers', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/series');

  // «New series»: code, name, type F1 (by default), the business's year, prefix and next number.
  await shown(page).locator('[data-testid=invoice-series-add]').click();
  const form = openDialog(page, 'invoice-series-form');
  await expect(form).toBeVisible();
  await expect(form.locator('[data-testid=invoice-series-year] input')).toHaveValue(String(year));
  await form.locator('[data-testid=invoice-series-code] input').fill(CODE);
  await form.locator('[data-testid=invoice-series-name] input').fill(`e2e Online ${RUN}`);
  await form.locator('[data-testid=invoice-series-prefix] input').fill(PREFIX);
  await form.locator('[data-testid=invoice-series-next-number] input').fill('7');
  await flowShots(page, 'INVOICE-F12', async (p) => {
    await expect(openDialog(p, 'invoice-series-form')).toBeVisible();
  });
  await form.locator('[data-testid=invoice-series-form-submit]').click();
  await expect(form).toBeHidden();

  const created = await seriesOf(page);
  expect([created.current_number, created.next_number, created.format_locked]).toEqual([6, `${PREFIX}-${year}-000007`, false]);
  await shown(page).locator('[data-testid=invoice-series-search] input').fill(CODE);
  await expect(rowOf(page)).toContainText(`e2e Online ${RUN}`);
  await flowShots(page, 'INVOICE-F12-list', async (p) => {
    await expect(rowOf(p)).toBeVisible();
  });

  // Edit: code, type and year locked; the next number it will hand out; a new name.
  await rowOf(page).click();
  await expect(form).toBeVisible();
  await expect(form.locator('[data-testid=invoice-series-code] input')).toBeDisabled();
  await expect(form.locator('[data-testid=invoice-series-preview]')).toContainText(`${PREFIX}-${year}-000007`);
  await form.locator('[data-testid=invoice-series-name] input').fill(`e2e Web shop ${RUN}`);
  await form.locator('[data-testid=invoice-series-form-submit]').click();
  await expect(form).toBeHidden();
  await expect(rowOf(page)).toContainText(`e2e Web shop ${RUN}`);
  expect((await seriesOf(page)).name).toBe(`e2e Web shop ${RUN}`);

  // An invoice in it takes number 7; from then on prefix, format and next number are frozen.
  const issued = await api<{ id: string; number: string }>(context, A, 'POST', '/invoice/invoices', {
    series_code: CODE,
    customer_name: `e2e Serie ${RUN}`,
    customer_tax_id: '12345678Z',
    customer_address: 'Calle Sol 5, Madrid',
    lines: [{ description: `e2e Course ${RUN}`, quantity: '1', unit_price: 1000, tax_rate: '21' }],
  });
  expect(issued.status).toBe(201);
  issuedIds.add(issued.data.id);
  expect(issued.data.number).toBe(`${PREFIX}-${year}-000007`);

  // The table catches up by itself: «Current no.» 7.
  await expect(rowOf(page)).toContainText(/(?:NNNNNN|Current no\.)\s*7\s*(?:Active\s*)?Yes/);
  await rowOf(page).click();
  await expect(form.locator('[data-testid=invoice-series-format-locked]')).toBeVisible();
  for (const field of ['prefix', 'format', 'next-number']) {
    await expect(form.locator(`[data-testid=invoice-series-${field}] input`)).toBeDisabled();
  }
  await expect(form.locator('[data-testid=invoice-series-preview]')).toContainText(`${PREFIX}-${year}-000008`);
  await flowShots(page, 'INVOICE-F13', async (p) => {
    await expect(openDialog(p, 'invoice-series-form').locator('[data-testid=invoice-series-format-locked]')).toBeVisible();
  });
  await form.locator('[data-testid=invoice-series-form-cancel]').click();
  await expect(form).toBeHidden();

  const series = await seriesOf(page);
  const refused = await api<{ error: { code: string } }>(context, A, 'POST', '/invoice/series/update', { series_id: series.id, prefix: 'OTHER' });
  expect([refused.status, refused.data.error.code]).toEqual([409, 'invoice.series_locked']);
});

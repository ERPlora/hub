// Invoicing in Chrome, by hand (apps/invoice/WORKBOOK.md), against the real Sales, Customers and Taxes:
//   - INVOICE-F21: without the issuer, Invoices says nothing can be invoiced; «Set up» opens the issuer page,
//     the owner saves it and the notice goes;
//   - INVOICE-F16: the manual invoice found in Invoices by its customer;
//   - INVOICE-F03, F19, F08: a manual invoice from «New invoice» (the server's VAT and number), marked as
//     paid, then rectified (R1, its reason): the original is cancelled and links its rectifying one;
//   - INVOICE-F05: the full invoice (F3) of a ticket, in the customer's name; the ticket links it;
//   - an employee issues and marks paid, but never sees «Rectify».
// What this file creates is deleted after it, and the hub's issuer and numbering are left as found.
import { expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shown } from './helpers';
import { cleanUp as cleanCustomers } from './customer-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, openDialog, deliver, ensureIssuer, flowShots, invoiceOf, type InvoiceOut, issuedIds, issuerNow, type IssuerOut, restoreIssuer, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, stamp } from './sale-helpers';

const RUN = stamp();
const ISSUER = {
  'legal-name': 'e2e Peluquería Ana SL',
  'tax-id': 'B12345674',
  address: 'Calle Mayor 1',
  'postal-code': '28001',
  city: 'Madrid',
  province: 'Madrid',
};
let original: IssuerOut;
let comb: Product;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices');
  snapshotSeries();
  original = await issuerNow(context);
  comb = await createProduct(context, { name: `E2E Comb ${RUN}`, sku: `E2E-INV-C-${RUN}`, price: 605, tax_category_key: 'product.generic' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanInvoices();
  } finally {
    cleanSales();
    cleanCustomers();
    cleanInventory();
  }
});

/** The invoice the list API finds for `search` (server-side evidence; the spec records it for cleanup). */
async function issuedFor(page: Page, search: string): Promise<InvoiceOut> {
  const res = await api<{ rows: { id: string }[] }>(page.context(), A, 'GET', `/invoice/invoices?search=${encodeURIComponent(search)}&limit=10`);
  expect(res.data.rows, `one invoice for ${search}`).toHaveLength(1);
  issuedIds.add(res.data.rows[0].id);
  return invoiceOf(page.context(), res.data.rows[0].id);
}

test('INVOICE-F21: without the issuer Invoices says so; «Set up» opens it, the owner saves it and the notice goes', async ({ page, context }) => {
  // No issuer: a configured one loses its address (the hub's own comes back after).
  if (original.configured) psql("update invoice_issuer set address = ''");
  try {
    await login(page, A, '/invoice/invoices');
    const notice = shown(page).locator('[data-testid=invoice-issuer-notice]');
    await expect(notice).toContainText('You cannot invoice yet');
    await expect(notice).toContainText('No ticket or invoice can be issued until you set this up:');
    await flowShots(page, 'INVOICE-F21-notice', async (p) => {
      await expect(shown(p).locator('[data-testid=invoice-issuer-notice]')).toBeVisible();
    });
    await notice.locator('[data-testid=invoice-issuer-notice-setup]').click();
    await page.waitForURL(/\/invoice\/issuer$/);
    const form = shown(page);
    await expect(form.locator('[data-testid=invoice-issuer-missing]')).toBeVisible();
    for (const [hook, value] of Object.entries(ISSUER)) await form.locator(`[data-testid=invoice-issuer-${hook}] input`).fill(value);
    await form.locator('[data-testid=invoice-issuer-save]').click();
    await expect(page.locator('ion-toast').filter({ hasText: 'Issuer saved.' })).toBeVisible();
    await expect(form.locator('[data-testid=invoice-issuer-missing]')).toHaveCount(0);
    const saved = await issuerNow(context);
    expect([saved.configured, saved.legal_name, saved.tax_id, saved.address, saved.country]).toEqual([true, ISSUER['legal-name'], ISSUER['tax-id'], ISSUER.address, 'ES']);
    await flowShots(page, 'INVOICE-F21', async (p) => {
      await expect(shown(p).locator('[data-testid=invoice-issuer-legal-name] input')).toHaveValue(ISSUER['legal-name']);
    });
    // Back in Invoices, the notice is gone.
    await page.goto(`${A}/invoice/invoices`);
    await expect(shown(page).locator('[data-testid=invoice-list-row], [data-testid=invoice-list-empty]').first()).toBeVisible();
    await expect(shown(page).locator('[data-testid=invoice-issuer-notice]')).toHaveCount(0);
  } finally {
    // The hub's own issuer back; with none before, the run's stays for the next tests and goes at the end.
    await restoreIssuer(context, original);
  }
});

test('INVOICE-F03, F19 and F08: a manual invoice is issued, marked as paid and rectified', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  await ensureIssuer(context);
  const customer = `e2e Cliente ${RUN}`;

  // «New invoice»: the recipient, one line WITHOUT VAT, its VAT %; the server computes and numbers it.
  await shown(page).locator('[data-testid=invoice-list-add]').click();
  const dialog = openDialog(page, 'invoice-create');
  await expect(dialog).toBeVisible();
  await dialog.locator('[data-testid=invoice-recipient-name] input').fill(customer);
  await dialog.locator('[data-testid=invoice-recipient-tax-id] input').fill('12345678Z');
  await dialog.locator('[data-testid=invoice-recipient-address] input').fill('Calle Sol 5, 28013 Madrid');
  await dialog.locator('[data-testid=invoice-line-1-description] input').fill(`e2e Consulting ${RUN}`);
  await dialog.locator('[data-testid=invoice-line-1-quantity] input').fill('2');
  await dialog.locator('[data-testid=invoice-line-1-price] input').fill('50');
  await expect(dialog.locator('[data-testid=invoice-line-1-tax-rate] input')).toHaveValue('21');
  await dialog.locator('[data-testid=invoice-create-notes] input').fill(`e2e manual ${RUN}`);
  await flowShots(page, 'INVOICE-F03', async (p) => {
    await expect(openDialog(p, 'invoice-create')).toBeVisible();
  });
  await dialog.locator('[data-testid=invoice-create-submit]').click();
  await expect(dialog).toBeHidden();

  const invoice = await issuedFor(page, customer);
  expect([invoice.invoice_type, invoice.status, invoice.total_amount]).toEqual(['F1', 'issued', 12100]);

  // The list paints it by itself: found by its customer, «Issued», 121.00.
  await shown(page).locator('[data-testid=invoice-list-search] input').fill(customer);
  const row = shown(page).locator('[data-testid=invoice-list-row]', { hasText: invoice.number }).first();
  await expect(row).toContainText(/121[.,]00/);
  await expect(row.locator('[data-testid=invoice-list-status]')).toHaveText('Issued');
  await flowShots(page, 'INVOICE-F16', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-list-row]', { hasText: invoice.number }).first()).toBeVisible();
  });

  // Its card: 100.00 + 21 % VAT 21.00 = 121.00; «Mark as paid», asked first.
  await row.click();
  await page.waitForURL(new RegExp(`/invoice/invoices/${invoice.id}$`));
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-base]')).toContainText(/100[.,]00/);
  await expect(detail.locator('[data-testid=invoice-detail-tax-amount]').first()).toContainText(/21[.,]00/);
  await expect(detail.locator('[data-testid=invoice-detail-total]')).toContainText(/121[.,]00/);
  await detail.locator('[data-testid=invoice-detail-mark-paid]').click();
  const confirm = page.locator('ion-modal').filter({ hasText: `Mark ${invoice.number} as paid?` }).last();
  await flowShots(page, 'INVOICE-F19', async () => {
    await expect(confirm).toBeVisible();
  });
  await confirm.locator('.ep-form-modal__submit').click();
  await expect(confirm).toBeHidden();
  await expect(detail.locator('[data-testid=invoice-detail-status]')).toHaveText('Paid');
  await expect(detail.locator('[data-testid=invoice-detail-paid-at]')).toBeVisible();
  await expect(detail.locator('[data-testid=invoice-detail-mark-paid]')).toHaveCount(0);

  // «Rectify»: R1 by default, its reason; the result in the same window, the original cancelled.
  await detail.locator('[data-testid=invoice-detail-rectify]').click();
  const rectify = openDialog(page, 'invoice-rectify');
  await expect(rectify).toBeVisible();
  await expect(rectify.locator('[data-testid=invoice-rectify-note]')).toBeVisible();
  await rectify.locator('[data-testid=invoice-rectify-reason] textarea').fill(`e2e wrong amount ${RUN}`);
  await rectify.locator('[data-testid=invoice-rectify-submit]').click();
  await expect(rectify.locator('[data-testid=invoice-rectify-done]')).toContainText(`${invoice.number} is cancelled`);
  await flowShots(page, 'INVOICE-F08', async (p) => {
    await expect(openDialog(p, 'invoice-rectify').locator('[data-testid=invoice-rectify-done]')).toBeVisible();
  });
  await rectify.locator('[data-testid=invoice-rectify-close-result]').click();
  await expect(rectify).toBeHidden();
  await expect(detail.locator('[data-testid=invoice-detail-status]')).toHaveText('Cancelled');

  const after = await invoiceOf(context, invoice.id);
  const rectifying = after.rectifications[0];
  issuedIds.add(rectifying.id);
  const rectified = await invoiceOf(context, rectifying.id);
  expect([after.status, rectified.invoice_type, rectified.total_amount, rectified.rectifies?.number]).toEqual(['cancelled', 'R1', -12100, invoice.number]);
  await expect(detail.locator('[data-testid=invoice-detail-rectifications-link]')).toHaveText(rectifying.number);
  await flowShots(page, 'INVOICE-F08-cancelled', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-detail-status]')).toHaveText('Cancelled');
  });
});

test('INVOICE-F05: the customer asks for the full invoice of their ticket, an F3 in their name', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/invoice/invoices');
  await ensureIssuer(context);
  const sale = await chargeByApi(context, { lines: [{ product: comb.sku }], payments: [{ method: 'card' }] });
  const ticket = await deliver(context, 'sale.sale.completed', sale.id);
  expect([ticket.invoice_type, ticket.total_amount]).toEqual(['F2', 605]);

  await page.goto(`${A}/invoice/invoices/${ticket.id}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-type]')).toHaveText('Ticket (F2)');
  await detail.locator('[data-testid=invoice-detail-substitute]').click();
  const dialog = openDialog(page, 'invoice-substitute');
  await expect(dialog.locator('[data-testid=invoice-substitute-intro]')).toBeVisible();
  await dialog.locator('[data-testid=invoice-recipient-name] input').fill(`e2e Talleres F3 ${RUN}`);
  await dialog.locator('[data-testid=invoice-recipient-tax-id] input').fill('B12345674');
  await dialog.locator('[data-testid=invoice-recipient-address] input').fill('Calle Luna 3, Madrid');
  await flowShots(page, 'INVOICE-F05', async (p) => {
    await expect(openDialog(p, 'invoice-substitute')).toBeVisible();
  });
  await dialog.locator('[data-testid=invoice-substitute-submit]').click();
  await expect(dialog).toBeHidden();

  // The F3 opens: same figures, the customer's name, the ticket it replaces.
  const replaced = await invoiceOf(context, ticket.id);
  const full = replaced.substituted_by!;
  issuedIds.add(full.id);
  await page.waitForURL(new RegExp(`/invoice/invoices/${full.id}$`));
  const f3 = shown(page);
  await expect(f3.locator('[data-testid=invoice-detail-type]')).toHaveText('Invoice replacing a ticket (F3)');
  await expect(f3.locator('[data-testid=invoice-detail-customer]')).toHaveText(`e2e Talleres F3 ${RUN}`);
  await expect(f3.locator('[data-testid=invoice-detail-total]')).toContainText(/6[.,]05/);
  await expect(f3.locator('[data-testid=invoice-detail-substitutes-link]')).toHaveText(ticket.number);
  await flowShots(page, 'INVOICE-F05-f3', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-detail-substitutes-link]')).toBeVisible();
  });
});

test('INVOICE-F03 and F19 as an employee: issues and marks paid, never rectifies', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/invoice/invoices', EMPLOYEE);
  const created = await api<InvoiceOut>(context, A, 'POST', '/invoice/invoices', {
    customer_name: `e2e Empleado ${RUN}`,
    customer_tax_id: '12345678Z',
    customer_address: 'Calle Sol 5, Madrid',
    lines: [{ description: `e2e Cut ${RUN}`, quantity: '1', unit_price: 1000, tax_rate: '21' }],
  });
  expect(created.status, `an employee issues: ${JSON.stringify(created.data)}`).toBe(201);
  issuedIds.add(created.data.id);

  await page.goto(`${A}/invoice/invoices/${created.data.id}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-title]')).toHaveText(`Invoice ${created.data.number}`);
  await expect(detail.locator('[data-testid=invoice-detail-mark-paid]')).toBeVisible();
  await expect(detail.locator('[data-testid=invoice-detail-rectify]')).toHaveCount(0);
  const refused = await api<{ error: { code: string } }>(context, A, 'POST', '/invoice/invoices/rectify', { invoice_id: created.data.id, reason: 'e2e no' });
  expect([refused.status, refused.data.error.code]).toEqual([403, 'permission_denied']);
  await flowShots(page, 'INVOICE-F19-employee', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-detail-mark-paid]')).toBeVisible();
  });
});

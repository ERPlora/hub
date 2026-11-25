// «Send by email» of an invoice (INVOICE-F26) in Chrome: the window proposes the customer's email, what it sends is told on
// the page by itself, and it can be sent again to another address.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, settled, shown, signedInSpanish } from './helpers';
import { cutLabels } from './field-labels';
import { cleanInvoices, flowShots, issueByHand, openDialog, readyToInvoice } from './invoice-helpers';
import { stamp } from './sale-helpers';

const CUSTOMER = `e2e Correo ${stamp()}`;
const ADDRESS = 'ana.lopez@example.com';
let invoice: { id: string; number: string };

test.beforeAll(async ({ browser }) => {
  const context = await readyToInvoice(browser);
  const card = await api<{ id: string }>(context, A, 'POST', '/customer/customers', { name: CUSTOMER, email: ADDRESS });
  expect(card.status, JSON.stringify(card.data)).toBe(201);
  invoice = await issueByHand(context, {
    customer_id: card.data.id,
    customer_name: CUSTOMER,
    customer_tax_id: 'B12345674',
    customer_address: 'Calle Luna 3',
    lines: [{ description: 'Consultoría', quantity: '1', unit_price: 10000, tax_rate: '21' }],
  });
  await context.close();
});

test.afterAll(() => cleanInvoices());

async function open(page: Page): Promise<void> {
  await page.goto(`${A}/invoice/invoices/${invoice.id}`);
  await expect(shown(page).locator('[data-testid=invoice-detail-title]')).toContainText(invoice.number);
}

async function windowOf(page: Page): Promise<Locator> {
  await shown(page).locator('[data-testid=invoice-detail-email]').click();
  const dialog = openDialog(page, 'invoice-email');
  await expect(dialog).toBeVisible();
  return dialog;
}

const address = (dialog: Locator): Locator => dialog.locator('[data-testid=invoice-email-to] input');
const told = (page: Page): Locator => shown(page).locator('[data-testid=invoice-detail-emailed]');

test('it goes to the customer’s email, and the page says to whom and when by itself', async ({ page }) => {
  await login(page, A, '/invoice/invoices');
  await open(page);
  const dialog = await windowOf(page);
  await expect(address(dialog)).toHaveValue(ADDRESS);

  await dialog.locator('[data-testid=invoice-email-submit]').click();

  await expect(dialog).toBeHidden();
  await expect(told(page)).toHaveText([new RegExp(`^\\s*Sent to ${ADDRESS} on .*\\d{4}`)]);
  await expect(shown(page).locator('[data-testid=invoice-detail-email-failed]')).toHaveCount(0);
  await flowShots(page, 'F26', async (shot) => {
    await expect(told(shot).first()).toBeVisible();
  });
});

test('it can be sent again to another address, with the keyboard alone', async ({ page }) => {
  await login(page, A, '/invoice/invoices');
  await open(page);
  await shown(page).locator('[data-testid=invoice-detail-email] button').focus();
  await page.keyboard.press('Enter');
  const dialog = openDialog(page, 'invoice-email');
  await expect(dialog).toBeVisible();
  await address(dialog).fill('facturas@example.com');
  await address(dialog).press('Enter');

  await expect(dialog).toBeHidden();
  await expect(told(page).first()).toContainText('Sent to facturas@example.com');
  await expect(told(page)).toHaveCount(2);
});

test('what is no address is said under its field and nothing is sent', async ({ page }) => {
  await login(page, A, '/invoice/invoices');
  await open(page);
  const before = await told(page).count();
  const dialog = await windowOf(page);
  await address(dialog).fill('ana@');
  await dialog.locator('[data-testid=invoice-email-submit]').click();

  await expect(dialog.locator('[data-testid=invoice-email-to]')).toHaveClass(/ion-invalid/);
  await expect(dialog).toBeVisible();
  expect(await told(page).count()).toBe(before);
});

for (const [label, width, height] of [['375', 375, 667], ['820', 820, 1180], ['1280', 1280, 720]] as const) {
  test(`in Spanish the window fits at ${label}px, with its label whole`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, { width, height }, '/invoice/invoices');
    await open(page);
    const dialog = await windowOf(page);
    await settled(page);
    await expect(dialog.locator('ion-title')).toHaveText(`Enviar la factura ${invoice.number} por correo`);
    expect(await cutLabels(dialog)).toEqual([]);
    const submit = (await dialog.locator('[data-testid=invoice-email-submit]').boundingBox())!;
    expect(submit.y + submit.height).toBeLessThanOrEqual(height);
    expect(submit.x + submit.width).toBeLessThanOrEqual(width);
    await context.close();
  });
}

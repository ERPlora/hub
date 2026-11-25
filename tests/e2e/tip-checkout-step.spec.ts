// flow: TIP-F02 — with Tips on and «Ask for a tip at the charge» turned on, the till's Charge sheet shows the «Tip» row
// of the payment method chosen, opening on the suggestion the settings mark; the card charges the sale and the tip
// together, the sale's payment carries the tip apart from its total, and the tip is recorded with that sale. Seen at a
// phone, an Android tablet on its side and a desk. What this file makes is deleted after it, and the settings and the
// apps it changed go back as they were.
import { expect, test } from '@playwright/test';

import { A, api, capture, login, psql, saveSessionForTheSweep, shown, turnOffTurnedOn, turnOnMissing } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { addToTill, cleanSales, stamp } from './sale-helpers';

const RUN = stamp();
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '1280', width: 1280, height: 800 },
  { label: '1440', width: 1440, height: 900 },
];

interface Method {
  id: string;
  type: string;
}
interface Settings {
  enabled: boolean;
  preselected: number;
}
interface Tip {
  sale_number: string;
  method_type: string;
  amount: number;
  status: string;
}
interface Sale {
  number: string;
  total: number;
  payments: { method_id: string; amount: number; extra: number; extra_label: string }[];
}

const turnedOn: string[] = [];
let before: Settings;
let product: Product;
let card: Method;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await turnOnMissing(context, A, ['tip'], turnedOn);
  before = (await api<Settings>(context, A, 'GET', '/tip/settings')).data;
  const saved = await api(context, A, 'POST', '/tip/settings', { enabled: true, preselected: 2 });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  const methods = await api<{ rows: Method[] }>(context, A, 'GET', '/sale/payment_methods?limit=100');
  card = methods.data.rows.find((row) => row.type === 'card')!;
  product = await createProduct(context, { name: `E2E Tip ${RUN}`, sku: `E2E-TIP-${RUN}`, price: 1000 });
  await context.close();
});

test.afterAll(async ({ browser }) => {
  // A tip keeps its sale: it goes first, or the sales of this run could not be deleted.
  psql(`delete from tip_tip where sale_id in (select sale_id from sale_saleline where sku = 'E2E-TIP-${RUN}')`);
  cleanSales();
  cleanInventory();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await api(context, A, 'POST', '/tip/settings', { enabled: before.enabled, preselected: before.preselected });
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

test('TIP-F02: the Charge sheet proposes the tips of the payment method, and the tip chosen is charged and recorded with its sale', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await saveSessionForTheSweep(page.context());
  await addToTill(page, product);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  const step = sheet.locator('[data-testid=tip-step]');
  await expect(step).toBeVisible();
  await sheet.locator(`[data-testid=sale-checkout-method-${card.id}]`).click();

  // The settings mark the second suggestion: 5 % of €10.00.
  // Ionic hands aria-pressed to the native button inside each ion-button.
  await expect(step.locator('[data-testid=tip-step-suggestion-1] button')).toHaveAttribute('aria-pressed', 'true');
  await expect(step.locator('[data-testid=tip-step-none] button')).toHaveAttribute('aria-pressed', 'false');
  await expect(step.locator('[data-testid=tip-step-suggestion-1]')).toContainText(/0[.,]50/);
  await expect(step.locator('[data-testid=tip-step-none]')).toBeVisible();
  await expect(sheet.locator('[data-testid=sale-checkout-added]')).toContainText(/\+ .*0[.,]50.* (tip|de propina)/);
  await expect(sheet.locator('[data-testid=sale-checkout-confirm]')).toContainText(/10[.,]50/);
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(step).toBeInViewport({ ratio: 0.5 });
    await capture(page, `tip-checkout-step-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // «Other amount» takes what is typed.
  await step.locator('[data-testid=tip-step-custom]').click();
  await step.locator('[data-testid=tip-step-amount] input').fill('1,20');
  await expect(sheet.locator('[data-testid=sale-checkout-confirm]')).toContainText(/11[.,]20/);
  await capture(page, 'tip-checkout-step-other-amount-1440');

  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  await expect(page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]')).toBeVisible();

  const tips = await api<{ rows: Tip[] }>(page.context(), A, 'GET', '/tip/tips?limit=5');
  const tip = tips.data.rows[0];
  expect([tip.method_type, tip.amount, tip.status]).toEqual(['card', 120, 'active']);
  const sale = await api<Sale>(page.context(), A, 'GET', `/sale/sales/detail?sale=${tip.sale_number}`);
  expect(sale.status, JSON.stringify(sale.data)).toBe(200);
  expect(sale.data.total).toBe(1000);
  expect(sale.data.payments.map((payment) => [payment.method_id, payment.amount, payment.extra, payment.extra_label])).toEqual([
    [card.id, 1000, 120, expect.stringMatching(/^(Tip|Propina)$/)],
  ]);
});

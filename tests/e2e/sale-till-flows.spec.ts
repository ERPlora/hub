// flow: SALE-F03, SALE-F09, SALE-F10, SALE-F14, SALE-F15, SALE-F16, SALE-F17, SALE-F18, SALE-F21 — the till's
// everyday actions in Chrome, against the real Inventory, Taxes and Staff, no mocks: an open-price line by its
// section and fruit sold by weight; a line discounted, another on the house, a third sold by someone of the team
// and the guest check that shows them; a check charged part by card and part in cash; a check parked and taken
// back from «Open checks», and another deleted there. Each screen in 390×844, 834×1194 and 1440×900. What a run
// creates — its products `E2E-TILL-<run>-…`, its section «e2e Fruit <run>», its team member «E2E Till <run>», its
// checks and sales — is deleted after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanSales, drawerOff, newestSaleOf, restoreDrawer, shots, stamp } from './sale-helpers';

const RUN = stamp();
const SECTION = `e2e Fruit ${RUN}`;
const MEMBER = `E2E Till ${RUN}`;
let coffee: Product;
let steak: Product;
let cake: Product;
let apples: Product;
let sectionId: string;
let memberId: string;

test.beforeAll(async ({ browser }) => {
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  coffee = await createProduct(context, { name: `E2E Coffee ${RUN}`, sku: `E2E-TILL-${RUN}-C`, price: 150, tax_category_key: 'restaurant.drink' });
  steak = await createProduct(context, { name: `E2E Steak ${RUN}`, sku: `E2E-TILL-${RUN}-S`, price: 2000, tax_category_key: 'restaurant.drink' });
  cake = await createProduct(context, { name: `E2E Cake ${RUN}`, sku: `E2E-TILL-${RUN}-K`, price: 400, tax_category_key: 'restaurant.drink' });
  apples = await createProduct(context, {
    name: `E2E Apples ${RUN}`,
    sku: `E2E-TILL-${RUN}-A`,
    price: 300,
    unit: 'kg',
    pricing_unit: 'kg',
    tax_category_key: 'product.super_reduced',
  });
  const section = await api<{ id: string }>(context, A, 'POST', '/sale/departments', { name: SECTION, tax_category_key: 'product.super_reduced' });
  expect(section.status, 'the section').toBe(201);
  sectionId = section.data.id;
  const member = await api<{ id: string }>(context, A, 'POST', '/staff/members', { first_name: MEMBER, last_name: 'Team' });
  expect(member.status, 'the team member').toBe(201);
  memberId = member.data.id;
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
    psql(`delete from staff_member where id = '${memberId}'`);
  } finally {
    restoreDrawer();
  }
});

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator(`[data-testid=pos-product-${coffee.id}]`).waitFor({ state: 'visible' });
}

/** The check on screen: on a phone it is the drawer behind its button. */
async function cartReady(page: Page): Promise<void> {
  await tillReady(page);
  const fab = page.locator('[data-testid=pos-cart-fab]');
  if (await fab.isVisible()) await fab.click();
  await shown(page).locator('[data-testid=pos-total]').waitFor({ state: 'visible' });
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
}

const lineOf = (page: Page, name: string) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: name }).first();
const lineId = async (page: Page, name: string) => (await lineOf(page, name).getAttribute('data-testid'))?.replace('pos-line-', '') ?? '';
const total = (page: Page) => shown(page).locator('[data-testid=pos-total]');

async function add(page: Page, product: Product): Promise<void> {
  await shown(page).locator(`[data-testid=pos-product-${product.id}]`).click();
  await expect(lineOf(page, product.name)).toBeVisible();
}

/** Starts from an empty check: whatever another test left on screen is parked out of the way. */
async function freshTill(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await expect(shown(page).locator('[data-testid=pos-cart-empty]')).toBeVisible();
}

async function methodIds(context: BrowserContext): Promise<Record<string, string>> {
  const methods = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  return Object.fromEntries(methods.data.rows.map((row) => [row.type, row.id]));
}

async function checkOf(context: BrowserContext, label: string): Promise<{ id: string; status: string } | undefined> {
  const res = await api<{ rows: { id: string; label: string; status: string }[] }>(context, A, 'GET', '/sale/orders?status=open&limit=100');
  return res.data.rows.find((row) => row.label === label);
}

test('SALE-F09, F10: an open-price line by its section, and apples sold by weight', async ({ page, context }) => {
  await freshTill(page);
  await shown(page).locator('[data-testid=pos-open-price-tile]').click();
  const amount = page.locator('[data-testid=pos-open-price-amount]:visible');
  await expect(amount).toBeVisible();
  for (const key of ['4', 'dot', '5']) await page.locator(`[data-testid=pos-key-${key}]:visible`).click();
  await expect(amount).toContainText('4.50');
  await page.locator(`[data-testid=pos-department-${sectionId}]:visible`).click();
  await page.locator('[data-testid=pos-open-price-add]:visible').click();
  await expect(lineOf(page, SECTION)).toContainText('4.50');

  await add(page, apples);
  const apple = lineOf(page, apples.name);
  await expect(apple.locator('[data-testid=pos-qty-unit]')).toHaveText('kg');
  const quantity = apple.locator('.pos-qty__field');
  await quantity.fill('0.75');
  await quantity.press('Enter');
  // The server values the weight: 0.75 kg × €3.00.
  await expect(apple).toContainText('2.25');
  await expect(total(page)).toContainText('6.75');
  await shots(page, 'APP-SALE-SALE-F09-F10', cartReady, { width: 1440, height: 900 });

  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await sheet.locator(`[data-testid=sale-checkout-method-${(await methodIds(context)).card}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  await page.locator('[data-testid=sale-document-close]').click();
  const sale = await newestSaleOf(context, apples.sku);
  expect(sale.lines.map((line) => [line.name, line.quantity, line.line_total])).toEqual([
    [SECTION, '1.000', 450],
    [apples.name, '0.750', 225],
  ]);
});

test('SALE-F14, F15, F16, F21: a line discounted, one on the house, one sold by a team member, and the guest check', async ({ page }) => {
  await freshTill(page);
  await add(page, steak);
  await add(page, cake);
  await add(page, coffee);

  // F14: −10 % on the steak, from its price tag.
  const steakId = await lineId(page, steak.name);
  await lineOf(page, steak.name).locator(`[data-testid=pos-line-${steakId}-discount]`).click();
  for (const key of ['1', '0']) await page.locator(`[data-testid=pos-key-${key}]:visible`).click();
  await expect(page.locator('[data-testid=pos-discount-value]:visible')).toContainText('10');
  await page.locator('[data-testid=pos-discount-apply]:visible').click();
  await expect(lineOf(page, steak.name)).toContainText('−10');
  await expect(lineOf(page, steak.name)).toContainText('18.00');

  // F15: the cake on the house.
  const cakeId = await lineId(page, cake.name);
  await lineOf(page, cake.name).locator(`[data-testid=pos-line-${cakeId}-gift]`).click();
  await expect(lineOf(page, cake.name)).toContainText('0.00');

  // F16: who serves the check from now on, then the coffee's line back to the check's professional.
  await shown(page).locator('[data-testid=pos-staff-chip]').click();
  await page.locator(`[data-testid=pos-staff-${memberId}]:visible`).click();
  await expect(shown(page).locator('[data-testid=pos-staff-chip]')).toContainText(MEMBER);
  await add(page, apples);
  const appleId = await lineId(page, apples.name);
  await expect(lineOf(page, apples.name).locator(`[data-testid=pos-line-${appleId}-staff]`)).toContainText(MEMBER);
  await expect(total(page)).toContainText('22.50');
  await shots(page, 'APP-SALE-SALE-F14-F15-F16', cartReady, { width: 1440, height: 900 });

  // F21: the guest check with the lines, the discount and the total; never an invoice.
  await shown(page).locator('[data-testid=pos-prebill]').click();
  const prebill = page.locator('[data-testid=pos-prebill-paper]:visible');
  await expect(prebill).toContainText(steak.name);
  await expect(prebill).toContainText('22.50');
  await shots(
    page,
    'APP-SALE-SALE-F21',
    async (p) => {
      await p.locator('[data-testid=pos-prebill-paper]:visible').waitFor({ state: 'visible' });
    },
    { width: 1440, height: 900 },
  );
  await page.locator('[data-testid=pos-prebill-close]:visible').click();
  await expect(prebill).toBeHidden();
});

test('SALE-F03: a check charged part by card and the rest in cash, with its change', async ({ page, context }) => {
  await freshTill(page);
  await add(page, steak);
  await expect(total(page)).toContainText('20.00');
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  const byType = await methodIds(context);
  await sheet.locator('[data-testid=sale-checkout-split]').click();
  await expect(sheet.locator('[data-testid=sale-checkout-remaining]')).toContainText('20.00');
  await sheet.locator(`[data-testid=sale-checkout-method-${byType.card}]`).click();
  for (const key of ['1', '2']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await sheet.locator('[data-testid=sale-checkout-add-leg]').click();
  await expect(sheet.locator('[data-testid=sale-checkout-remaining]')).toContainText('8.00');
  await sheet.locator(`[data-testid=sale-checkout-method-${byType.cash}]`).click();
  for (const key of ['1', '0']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await expect(sheet.locator('[data-testid=sale-checkout-change]')).toContainText('2.00');
  await sheet.locator('[data-testid=sale-checkout-add-leg]').click();
  await expect(sheet.locator('[data-testid=sale-checkout-leg]')).toHaveCount(2);
  await shots(
    page,
    'APP-SALE-SALE-F03',
    async (p) => {
      await p.locator('[data-testid=sale-checkout-modal] [data-testid=sale-checkout-leg]').first().waitFor({ state: 'visible' });
    },
    { width: 1440, height: 900 },
  );
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  await page.locator('[data-testid=sale-document-close]').click();
  const sale = await newestSaleOf(context, steak.sku);
  expect(sale.payments.map((p) => [p.method_type, p.amount, p.tendered, p.change])).toEqual([
    ['card', 1200, 1200, 0],
    ['cash', 800, 1000, 200],
  ]);
});

test('SALE-F17, F18: a check parked and taken back from «Open checks», another deleted there', async ({ page, context }) => {
  const kept = `e2e Terrace ${RUN}`;
  const dropped = `e2e Bar ${RUN}`;
  await freshTill(page);
  for (const [label, product] of [
    [dropped, cake],
    [kept, coffee],
  ] as const) {
    await add(page, product);
    await shown(page).locator('ion-button[data-testid=pos-park]').click();
    const name = page.locator('input[data-testid=pos-park-name]:visible');
    await name.fill(label);
    await page.locator('[data-testid=pos-park-confirm]:visible').click();
    await expect(page.locator('ion-toast').filter({ hasText: `Parked as “${label}”` })).toBeVisible();
    await expect(shown(page).locator('[data-testid=pos-cart-empty]')).toBeVisible();
  }
  const keptCheck = await checkOf(context, kept);
  const droppedCheck = await checkOf(context, dropped);
  expect([keptCheck?.status, droppedCheck?.status]).toEqual(['open', 'open']);

  await shown(page).locator('[data-testid=pos-open-checks]').click();
  const list = shown(page).locator('[data-testid=pos-checks]');
  await expect(list.locator(`[data-testid=pos-parked-${keptCheck?.id}]`)).toContainText(kept);
  await shots(
    page,
    'APP-SALE-SALE-F17-F18',
    async (p) => {
      await cartReady(p);
      const open = shown(p).locator('[data-testid=pos-checks]');
      if (!(await open.isVisible())) await shown(p).locator('[data-testid=pos-open-checks]').click();
      await open.waitFor({ state: 'visible' });
    },
    { width: 1440, height: 900 },
  );
  if (!(await list.isVisible())) await shown(page).locator('[data-testid=pos-open-checks]').click();

  // F18: the bin arms on the first tap and deletes on the second.
  const bin = list.locator(`[data-testid=pos-parked-${droppedCheck?.id}-delete]`);
  await bin.click();
  await expect(bin).toHaveAttribute('aria-label', 'Tap again to delete — this voids the check');
  await bin.click();
  await expect(list.locator(`[data-testid=pos-parked-${droppedCheck?.id}]`)).toHaveCount(0);
  expect(await checkOf(context, dropped)).toBeUndefined();

  // F17: back on screen with its line.
  await list.locator(`[data-testid=pos-parked-${keptCheck?.id}]`).click();
  await expect(lineOf(page, coffee.name)).toBeVisible();
  await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(kept);
});

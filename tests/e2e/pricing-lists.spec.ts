// Price Lists in Chrome, hidden (WORKBOOK PRICING-F01 to F13), with the real Inventory and Customers
// apps: the owner creates a VIP list for a customer group of Customers (a repeated code is refused),
// opens it and puts the price of an Inventory product in it, creates a 10 % rule on that product, and the
// server prices the VIP customer's line with the list and the rule (`pricing.price.resolve`); the rule is
// deactivated (asking first) and the discount goes. Each screen is captured in three viewports.
// Everything this spec creates is named «E2E Price …» (codes E2EPR…) and removed before and after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';

const TAG = 'E2E Price';
const CODE = 'E2EPR';
const VIEWPORTS = {
  desktop: { width: 1280, height: 860 },
  tablet: { width: 820, height: 1180 },
  phone: { width: 390, height: 844 },
} as const;
const run = Date.now().toString(36).toUpperCase();

/** Deletes what this spec created, in every app it touched. */
function cleanUp(): void {
  const products = `select id from inventory_product where sku like '${CODE}-%'`;
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const groups = `select id from customer_customergroup where name like '${TAG}%'`;
  psql(
    [
      `delete from pricing_priceitem where price_list_id in (select id from pricing_pricelist where code like '${CODE}%') or product_id in (${products})`,
      `delete from pricing_pricelist where code like '${CODE}%'`,
      `delete from pricing_discountrule where code like '${CODE}%'`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      `delete from inventory_product where sku like '${CODE}-%'`,
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer_groups where customer_id in (${customers}) or customergroup_id in (${groups})`,
      `delete from customer_customer where name like '${TAG}%'`,
      `delete from customer_customergroup where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

async function ownerPage(browser: import('@playwright/test').Browser, next: string, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next);
  return { context, page };
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status = 201): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

/** Picks the option of a `Combo` whose text holds `text`, searching it by `query`. Only a search the Combo
 *  itself says failed (its `-error` state: runserver restarting because another session saved a `.py`
 *  file, `ERR_CONNECTION_REFUSED`) is asked again, with its «Retry», once `/healthz` answers again, twice
 *  at most; anything else fails at once. */
async function pick(page: Page, testid: string, query: string, text: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`);
  const option = page.locator(`[data-testid^=${testid}-option-]`, { hasText: text }).first();
  const failed = page.locator(`[data-testid=${testid}-error]`);
  await input.click();
  await input.fill(query);
  for (let attempt = 1; ; attempt += 1) {
    await option.or(failed).first().waitFor({ state: 'visible' });
    if (await option.isVisible()) break;
    if (attempt === 3) throw new Error(`pick ${testid}: the search kept failing: ${await failed.innerText()}`);
    console.warn(`pick ${testid}: the search failed (attempt ${attempt}); asking it again once the server answers`);
    await expect
      .poll(async () => (await page.request.get(`${A}/healthz`).catch(() => null))?.status() ?? 0, { timeout: 30_000 })
      .toBe(200);
    await page.locator(`[data-testid=${testid}-retry]`).click();
  }
  await option.click();
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

const ready = (page: Page, table: string) =>
  shown(page).locator(`[data-testid=${table}-empty], [data-testid=${table}-row]`).first().waitFor({ state: 'visible' });

test('A VIP list with an Inventory product, a rule, and the price of a VIP customer’s line', async ({ browser }) => {
  const group = `${TAG} VIP ${run}`;
  const customerName = `${TAG} Lucía ${run}`;
  const productName = `${TAG} Shampoo ${run}`;
  const sku = `${CODE}-${run}`;
  const listCode = `${CODE}${run}`;
  const ruleCode = `${CODE}R${run}`;
  const { context, page } = await ownerPage(browser, '/pricing/lists', VIEWPORTS.desktop);
  let listId = '';
  try {
    // Setup through the other apps' own APIs: a product of Inventory, a group and a card of Customers.
    const product = await post<{ id: string }>(context, '/inventory/products', {
      name: productName,
      sku,
      price: 1500,
      tax_category_key: 'product.generic',
    });
    await post(context, '/customer/groups', { name: group });
    const customer = await post<{ id: string }>(context, '/customer/customers', { name: customerName });
    await post(context, '/customer/customers/set_groups', { id: customer.id, groups: [group] }, 200);

    // A new list for the group (PRICING-F02).
    let view = shown(page);
    await expect(view.locator('h2').first()).toHaveText('Price lists');
    await ready(page, 'pricing-lists');
    await view.locator('[data-testid=pricing-lists-add]').click();
    await page.locator('[data-testid=pricing-list-form-code] input').fill(listCode);
    await page.locator('[data-testid=pricing-list-form-name] input').fill(`${TAG} VIP members`);
    await pick(page, 'pricing-list-form-group', run, group);
    await page.screenshot({ path: shot('pricing-list-new') });
    await page.locator('[data-testid=pricing-list-form-submit]').click();
    const row = view.locator('[data-testid=pricing-lists-row]', { hasText: listCode });
    await expect(row).toContainText(group);
    await expect(row).toContainText('Business default');

    // The same code in another case is refused under Code, and nothing is created.
    await view.locator('[data-testid=pricing-lists-add]').click();
    await page.locator('[data-testid=pricing-list-form-code] input').fill(listCode.toLowerCase());
    await page.locator('[data-testid=pricing-list-form-name] input').fill(`${TAG} Again`);
    await page.locator('[data-testid=pricing-list-form-submit]').click();
    await expect(page.locator('[data-testid=pricing-list-form-code]')).toContainText(
      'A price list with that code already exists. Pick a different code.',
    );
    await page.screenshot({ path: shot('pricing-list-duplicate') });
    await page.locator('[data-testid=pricing-list-form-cancel]').click();
    expect(psql(`select count(*) from pricing_pricelist where lower(code) = lower('${listCode}')`)).toBe('1');

    // The list's detail: the price of the Inventory product from one unit (PRICING-F06, F07).
    await row.getByText(listCode).click();
    await page.waitForURL(/\/pricing\/lists\/[0-9a-f-]+$/);
    listId = page.url().split('/').pop()!;
    view = shown(page);
    await expect(view.locator('[data-testid=pricing-detail-summary]')).toContainText(group);
    await ready(page, 'pricing-items');
    await view.locator('[data-testid=pricing-items-add]').click();
    await pick(page, 'pricing-item-form-article', sku, productName);
    await page.locator('[data-testid=pricing-item-form-price] input').fill('12');
    await page.screenshot({ path: shot('pricing-item-new') });
    await page.locator('[data-testid=pricing-item-form-submit]').click();
    const itemRow = view.locator('[data-testid=pricing-items-row]', { hasText: productName });
    await expect(itemRow).toContainText('€12.00');
    await expect(itemRow).toContainText('€15.00');
    await page.screenshot({ path: shot('pricing-detail-desktop') });

    // A 10 % rule on that product (PRICING-F10).
    await page.goto(`${A}/pricing/lists`);
    view = shown(page);
    await ready(page, 'pricing-rules');
    await view.locator('[data-testid=pricing-rules-add]').click();
    await page.locator('[data-testid=pricing-rule-form-code] input').fill(ruleCode);
    await page.locator('[data-testid=pricing-rule-form-name] input').fill(`${TAG} Shampoo 10`);
    await page.locator('[data-testid=pricing-rule-form-percent] input').fill('10');
    await page.locator('[data-testid=pricing-rule-form-applies_to]').click();
    await page.locator('ion-popover ion-radio').filter({ hasText: /^\s*A product\s*$/ }).click();
    await expect(page.locator('[data-testid=pricing-rule-form-applies_to]')).toHaveJSProperty('value', 'product');
    await pick(page, 'pricing-rule-form-target', sku, productName);
    await page.screenshot({ path: shot('pricing-rule-new') });
    await page.locator('[data-testid=pricing-rule-form-submit]').click();
    const ruleRow = view.locator('[data-testid=pricing-rules-row]', { hasText: ruleCode });
    await expect(ruleRow).toContainText('10%');
    await expect(ruleRow).toContainText(productName);
    await page.screenshot({ path: shot('pricing-lists-desktop') });

    // The server prices the VIP customer's line: the list's 12.00 €, minus the rule's 10 % (PRICING-F13).
    const asked = `/pricing/prices/resolve?product=${encodeURIComponent(sku)}&customer=${encodeURIComponent(customerName)}&quantity=2`;
    const line = await api<{ unit_price: number; price_list_code: string; discount: number; total: number; rule_code: string }>(
      context,
      A,
      'GET',
      asked,
    );
    expect(line.status, JSON.stringify(line.data)).toBe(200);
    expect(line.data).toMatchObject({ unit_price: 1200, price_list_code: listCode, discount: 240, total: 2160, rule_code: ruleCode });

    // The rule is deactivated, asking first, and the discount goes (PRICING-F12).
    const ruleId = psql(`select id from pricing_discountrule where code = '${ruleCode}'`);
    await rowAction(page, 'pricing-rules', ruleId, 'deactivate');
    await expect(page.locator('ion-modal[data-testid=pricing-rules-deactivate]')).toContainText('will stop applying to new sales.');
    await page.locator('[data-testid=pricing-rules-deactivate-submit]').click();
    await expect(ruleRow).toHaveCount(0);
    const after = await api<{ unit_price: number; discount: number; rule_code: string | null }>(context, A, 'GET', asked);
    expect(after.data).toMatchObject({ unit_price: 1200, discount: 0, rule_code: null });
    expect(product.id).toBeTruthy();
  } finally {
    await context.close();
  }

  // The same screens on a tablet and on a phone (cards).
  for (const [name, viewport] of Object.entries(VIEWPORTS).filter(([key]) => key !== 'desktop')) {
    const { context: small, page: phone } = await ownerPage(browser, '/pricing/lists', viewport);
    try {
      await expect(shown(phone).getByText(listCode).first()).toBeVisible();
      await phone.screenshot({ path: shot(`pricing-lists-${name}`) });
      await phone.goto(`${A}/pricing/lists/${listId}`);
      await expect(shown(phone).getByText(productName).first()).toBeVisible();
      await phone.screenshot({ path: shot(`pricing-detail-${name}`) });
    } finally {
      await small.close();
    }
  }
});

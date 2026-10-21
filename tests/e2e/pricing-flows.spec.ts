// Price Lists, flow by flow, in Chrome against the real Inventory and Customers apps (apps/pricing/WORKBOOK.md),
// each flow with its screenshots `APP-PRICING-<flow>-<390|834|1440>`:
//   - PRICING-F01: the lists, searched; «Inactive» shows the deactivated one (pm#254); both sections have their
//     title (pricing#48) and, on a phone, a card says the list's name once (pricing#47);
//   - PRICING-F02: «+» creates a list; on a phone, a repeated code is said under «Code», in sight, and nothing
//     is created (pm#478, pricing#46);
//   - PRICING-F03: «Edit» opens «Editing price list — <name>» with what it has; the row shows the change;
//   - PRICING-F04: «Make general» asks first; the row says «General»;
//   - PRICING-F05: «Deactivate» asks first; the list waits under «Inactive» until «Activate»;
//   - PRICING-F06: the list's detail with its prices and the catalog's, thousands grouped (hub#1090);
//   - PRICING-F07: «+» puts an Inventory product's price from a quantity;
//   - PRICING-F08: «Edit» changes a price; «Remove» asks first and the price goes;
//   - PRICING-F09: the rules, each type with its value (pricing#28: an amount rule never says 0);
//   - PRICING-F10: «+» creates an amount-per-unit rule on every product;
//   - PRICING-F11: «Edit» opens «Editing rule — <name>»; the row shows the new priority;
//   - PRICING-F12: «Deactivate» asks first; the rule waits under «Inactive» until «Activate».
import { expect, type Page, test } from '@playwright/test';

import { A, login, psql, shown } from './helpers';
import {
  choose,
  cleanPricing,
  CODE,
  createProduct,
  DESKTOP,
  dialog,
  fill,
  filterStatus,
  pick,
  post,
  ready,
  row,
  rowAction,
  search,
  shootFlow,
  stamp,
  TAG,
} from './pricing-helpers';

test.use({ viewport: DESKTOP, locale: 'en-US' });
test.beforeAll(cleanPricing);
test.afterAll(cleanPricing);

const LISTS = 'pricing-lists';
const RULES = 'pricing-rules';
const ITEMS = 'pricing-items';

interface Named {
  id: string;
  code: string;
  name: string;
}

async function newList(page: Page, s: string, suffix: string, fields: Record<string, unknown> = {}): Promise<Named> {
  const code = `${CODE}${s}${suffix}`;
  const name = `${TAG} ${suffix} ${s}`;
  const made = await post<{ id: string }>(page.context(), '/pricing/price_lists', { code, name, ...fields });
  return { id: made.id, code, name };
}

async function newRule(page: Page, s: string, suffix: string, fields: Record<string, unknown>): Promise<Named> {
  const code = `${CODE}${s}${suffix}`;
  const name = `${TAG} ${suffix} ${s}`;
  const made = await post<{ id: string }>(page.context(), '/pricing/rules', { code, name, ...fields });
  return { id: made.id, code, name };
}

async function openLists(page: Page, filter: string): Promise<void> {
  await login(page, A, '/pricing/lists');
  await ready(page, LISTS);
  await ready(page, RULES);
  await search(page, LISTS, filter);
}

test('PRICING-F01: the lists, searched and filtered by status, on every screen size', async ({ page }) => {
  // flow: PRICING-F01
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const wholesale = await newList(page, s, 'WHOLESALE');
  const summer = await newList(page, s, 'SUMMER', { valid_from: '2026-07-01', valid_until: '2026-08-31' });
  await post(page.context(), '/pricing/price_lists/deactivate', { id: summer.id }, 200);
  await ready(page, LISTS);
  // Both sections have their title (pricing#48).
  await expect(shown(page).locator('h2', { hasText: /^Price lists$/ })).toBeVisible();
  await expect(shown(page).locator('h2', { hasText: /^Discount rules$/ })).toBeVisible();

  await search(page, LISTS, `${CODE}${s}`);
  await expect(row(page, LISTS, wholesale.code)).toBeVisible();
  await expect(row(page, LISTS, summer.code)).toHaveCount(0);
  await expect(row(page, LISTS, wholesale.code)).toContainText('Active');
  await shootFlow(page, 'PRICING-F01');

  // «Inactive» shows the deactivated one, and only it (pm#254); «All», both.
  await filterStatus(page, LISTS, 'Inactive');
  await expect(row(page, LISTS, summer.code)).toBeVisible();
  await expect(row(page, LISTS, summer.code)).toContainText('Inactive');
  await expect(row(page, LISTS, summer.code)).toContainText('Jul');
  await expect(row(page, LISTS, wholesale.code)).toHaveCount(0);
  await filterStatus(page, LISTS, 'All');
  await expect(row(page, LISTS, wholesale.code)).toBeVisible();
  await expect(row(page, LISTS, summer.code)).toBeVisible();

  // On a phone, the lists are cards that say their name once (pricing#47).
  await page.setViewportSize({ width: 390, height: 844 });
  const card = row(page, LISTS, wholesale.code);
  await expect(card).toBeVisible();
  await expect(card.getByText(wholesale.name, { exact: true })).toHaveCount(1);
});

test('PRICING-F02: a new list, and a repeated code said under Code in sight on a phone', async ({ page }) => {
  // flow: PRICING-F02
  const s = stamp();
  const code = `${CODE}${s}NEW`;
  const name = `${TAG} Members ${s}`;
  await openLists(page, `${CODE}${s}`);
  await shown(page).locator(`[data-testid=${LISTS}-add]`).click();
  const form = dialog(page, 'pricing-list-form');
  await expect(form).toContainText('New price list');
  await fill(page, 'pricing-list-form-code', code);
  await fill(page, 'pricing-list-form-name', name);
  await shootFlow(page, 'PRICING-F02');
  await page.locator('[data-testid=pricing-list-form-submit]').click();
  await expect(form).toBeHidden();
  const created = row(page, LISTS, code);
  await expect(created).toContainText(name);
  await expect(created).toContainText('Active');

  // On a phone, the same code in another case is refused under «Code», where it can be read (pm#478, pricing#46).
  await page.setViewportSize({ width: 390, height: 844 });
  await shown(page).locator(`[data-testid=${LISTS}-add]`).click();
  await fill(page, 'pricing-list-form-code', code.toLowerCase());
  await fill(page, 'pricing-list-form-name', `${TAG} Again ${s}`);
  await page.locator('[data-testid=pricing-list-form-submit]').click();
  const refusal = page.locator('[data-testid=pricing-list-form-code]').getByText(
    'A price list with that code already exists. Pick a different code.',
  );
  await expect(refusal).toBeInViewport();
  await expect(page.locator('[data-testid=pricing-list-form-submit]')).toBeInViewport();
  await page.locator('[data-testid=pricing-list-form-cancel]').click();
  expect(psql(`select count(*) from pricing_pricelist where lower(code) = lower('${code}')`)).toBe('1');
});

test('PRICING-F03: «Edit» opens the list with what it has and the row shows the change', async ({ page }) => {
  // flow: PRICING-F03
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const list = await newList(page, s, 'EDIT');
  await openLists(page, list.code);
  await rowAction(page, LISTS, list.id, 'edit');
  const form = dialog(page, 'pricing-list-form');
  await expect(form).toContainText(`Editing price list — ${list.name}`);
  await expect(page.locator('[data-testid=pricing-list-form-code] input')).toHaveValue(list.code);
  await fill(page, 'pricing-list-form-name', `${TAG} Renamed ${s}`);
  await shootFlow(page, 'PRICING-F03');
  await page.locator('[data-testid=pricing-list-form-submit]').click();
  await expect(form).toBeHidden();
  await expect(row(page, LISTS, list.code)).toContainText(`${TAG} Renamed ${s}`);
  expect(psql(`select name from pricing_pricelist where id = '${list.id}'`)).toBe(`${TAG} Renamed ${s}`);
});

test('PRICING-F04: «Make general» asks first and the row says General', async ({ page }) => {
  // flow: PRICING-F04
  const s = stamp();
  const previous = psql(`select id from pricing_pricelist where is_default`);
  try {
    await login(page, A, '/pricing/lists');
    const list = await newList(page, s, 'GENERAL');
    await openLists(page, list.code);
    await rowAction(page, LISTS, list.id, 'makeDefault');
    const confirm = dialog(page, 'pricing-list-default');
    await expect(confirm).toContainText(`${list.name} becomes the general price list`);
    await shootFlow(page, 'PRICING-F04');
    await page.locator('[data-testid=pricing-list-default-submit]').click();
    await expect(confirm).toBeHidden();
    await expect(row(page, LISTS, list.code)).toContainText('General');
    await expect(row(page, LISTS, list.code)).toContainText('Everybody');
    expect(psql(`select count(*) from pricing_pricelist where is_default`)).toBe('1');
  } finally {
    // The hub's own general list, if it had one, is general again.
    cleanPricing();
    if (previous) psql(`update pricing_pricelist set is_default = true where id = '${previous}'`);
  }
});

test('PRICING-F05: «Deactivate» asks first; the list waits under Inactive until «Activate»', async ({ page }) => {
  // flow: PRICING-F05
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const list = await newList(page, s, 'OFF');
  await openLists(page, list.code);
  await rowAction(page, LISTS, list.id, 'deactivate');
  const confirm = dialog(page, 'pricing-list-deactivate');
  await expect(confirm).toContainText(`${list.name} will stop applying to new sales. Its prices are kept.`);
  await shootFlow(page, 'PRICING-F05');
  await page.locator('[data-testid=pricing-list-deactivate-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(row(page, LISTS, list.code)).toHaveCount(0);

  await filterStatus(page, LISTS, 'Inactive');
  await expect(row(page, LISTS, list.code)).toContainText('Inactive');
  await rowAction(page, LISTS, list.id, 'activate');
  await expect(row(page, LISTS, list.code)).toHaveCount(0);
  await filterStatus(page, LISTS, 'Active');
  await expect(row(page, LISTS, list.code)).toContainText('Active');
  expect(psql(`select is_active from pricing_pricelist where id = '${list.id}'`)).toBe('t');
});

test('PRICING-F06: the detail shows the list and its prices beside the catalog’s', async ({ page }) => {
  // flow: PRICING-F06
  const s = stamp();
  await login(page, A, '/pricing/lists');
  // A long code (up to 50 characters) stays inside its cell of the summary.
  const list = await newList(page, s, 'DETAILOFAVERYLONGPRICELISTCODE');
  const dryer = await createProduct(page.context(), `${TAG} Dryer ${s}`, `${CODE}-DRY${s}`, 150000);
  const comb = await createProduct(page.context(), `${TAG} Comb ${s}`, `${CODE}-CMB${s}`, 300);
  await post(page.context(), '/pricing/price_items', { price_list_id: list.id, product_id: dryer.id, price: 123456 });
  await post(page.context(), '/pricing/price_items', { price_list_id: list.id, product_id: comb.id, price: 250 });
  await openLists(page, list.code);
  await rowAction(page, LISTS, list.id, 'open');
  await page.waitForURL(new RegExp(`/pricing/lists/${list.id}$`));
  await expect(shown(page).locator('[data-testid=pricing-detail-summary]')).toContainText(list.code);
  await ready(page, ITEMS);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const overflow = await shown(page)
      .locator('[data-testid=pricing-detail-code]')
      .evaluate((cell) => cell.scrollWidth - cell.clientWidth);
    expect(overflow, `the code overflows its cell by ${overflow}px at ${width}px`).toBeLessThanOrEqual(0);
  }
  await page.setViewportSize(DESKTOP);
  const dryerRow = row(page, ITEMS, `${TAG} Dryer ${s}`);
  // Thousands grouped from four digits on (hub#1090).
  await expect(dryerRow).toContainText('€1,234.56');
  await expect(dryerRow).toContainText('€1,500.00');
  await expect(row(page, ITEMS, `${TAG} Comb ${s}`)).toContainText('€2.50');
  await shootFlow(page, 'PRICING-F06');

  await search(page, ITEMS, `${CODE}-CMB${s}`);
  await expect(row(page, ITEMS, `${TAG} Comb ${s}`)).toBeVisible();
  await expect(dryerRow).toHaveCount(0);
});

test('PRICING-F07: «+» puts the price of an Inventory product from a quantity', async ({ page }) => {
  // flow: PRICING-F07
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const list = await newList(page, s, 'VOLUME');
  const sku = `${CODE}-GEL${s}`;
  const gel = `${TAG} Gel ${s}`;
  await createProduct(page.context(), gel, sku, 1000);
  await page.goto(`${A}/pricing/lists/${list.id}`);
  await ready(page, ITEMS);
  await shown(page).locator(`[data-testid=${ITEMS}-add]`).click();
  const form = dialog(page, 'pricing-item-form');
  await expect(form).toContainText('New price');
  await pick(page, 'pricing-item-form-article', sku, gel);
  await fill(page, 'pricing-item-form-min_quantity', '10');
  await fill(page, 'pricing-item-form-price', '8,50');
  await shootFlow(page, 'PRICING-F07');
  await page.locator('[data-testid=pricing-item-form-submit]').click();
  await expect(form).toBeHidden();
  const item = row(page, ITEMS, gel);
  await expect(item).toContainText('€8.50');
  await expect(item).toContainText('€10.00');
  await expect(item).toContainText('10');
  expect(psql(`select price || '@' || min_quantity from pricing_priceitem where price_list_id = '${list.id}'`)).toBe('850@10.000');
});

test('PRICING-F08: «Edit» changes a price; «Remove» asks first and the price goes', async ({ page }) => {
  // flow: PRICING-F08
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const list = await newList(page, s, 'CHANGE');
  const name = `${TAG} Mask ${s}`;
  const mask = await createProduct(page.context(), name, `${CODE}-MSK${s}`, 900);
  const item = await post<{ id: string }>(page.context(), '/pricing/price_items', {
    price_list_id: list.id,
    product_id: mask.id,
    price: 800,
  });
  await page.goto(`${A}/pricing/lists/${list.id}`);
  await ready(page, ITEMS);
  await rowAction(page, ITEMS, item.id, 'edit');
  const form = dialog(page, 'pricing-item-form');
  await expect(form).toContainText(`Editing price — ${name}`);
  await fill(page, 'pricing-item-form-price', '7.25');
  await page.locator('[data-testid=pricing-item-form-submit]').click();
  await expect(form).toBeHidden();
  await expect(row(page, ITEMS, name)).toContainText('€7.25');

  await rowAction(page, ITEMS, item.id, 'remove');
  const confirm = dialog(page, 'pricing-items-remove');
  // The quantity with the product's unit (Inventory's «ud»).
  await expect(confirm).toContainText(`The price of ${name} from 1 ud will be removed.`);
  await shootFlow(page, 'PRICING-F08');
  await page.locator('[data-testid=pricing-items-remove-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(row(page, ITEMS, name)).toHaveCount(0);
  await expect(shown(page).locator(`[data-testid=${ITEMS}-empty]`)).toContainText('This price list has no prices yet.');
});

test('PRICING-F09: the rules, each type with its value', async ({ page }) => {
  // flow: PRICING-F09
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const percent = await newRule(page, s, 'PCT', { rule_type: 'percent', percent: '10' });
  const amount = await newRule(page, s, 'AMT', { rule_type: 'fixed', amount: 50, applies_to: 'products' });
  const buyGet = await newRule(page, s, 'BXG', { rule_type: 'buy_x_get_y', buy_quantity: 2, get_quantity: 1 });
  const tiered = await newRule(page, s, 'TIER', {
    rule_type: 'tiered',
    tiers: [
      { min_quantity: '3', percent: '10' },
      { min_quantity: '6', percent: '15' },
    ],
    applies_to: 'services',
  });
  await ready(page, RULES);
  await search(page, RULES, `${CODE}${s}`);
  await expect(row(page, RULES, percent.code)).toContainText('10%');
  await expect(row(page, RULES, percent.code)).toContainText('Everything');
  // An amount rule says its amount, never 0 (pricing#28).
  await expect(row(page, RULES, amount.code)).toContainText('€0.50 per unit');
  await expect(row(page, RULES, amount.code)).toContainText('All products');
  await expect(row(page, RULES, buyGet.code)).toContainText('Buy 2, get 1');
  await expect(row(page, RULES, tiered.code)).toContainText('3+: 10%');
  await expect(row(page, RULES, tiered.code)).toContainText('6+: 15%');
  await expect(row(page, RULES, tiered.code)).toContainText('All services');
  await shootFlow(page, 'PRICING-F09');
});

test('PRICING-F10: «+» creates an amount-per-unit rule on every product', async ({ page }) => {
  // flow: PRICING-F10
  const s = stamp();
  const code = `${CODE}${s}R`;
  const name = `${TAG} Fifty off ${s}`;
  await login(page, A, '/pricing/lists');
  await ready(page, RULES);
  await search(page, RULES, `${CODE}${s}`);
  await shown(page).locator(`[data-testid=${RULES}-add]`).click();
  const form = dialog(page, 'pricing-rule-form');
  await expect(form).toContainText('New discount rule');
  await fill(page, 'pricing-rule-form-code', code);
  await fill(page, 'pricing-rule-form-name', name);
  await choose(page, page.locator('[data-testid=pricing-rule-form-rule_type]'), 'Amount per unit');
  await fill(page, 'pricing-rule-form-amount', '0,50');
  await choose(page, page.locator('[data-testid=pricing-rule-form-applies_to]'), 'All products');
  await shootFlow(page, 'PRICING-F10');
  await page.locator('[data-testid=pricing-rule-form-submit]').click();
  await expect(form).toBeHidden();
  const created = row(page, RULES, code);
  await expect(created).toContainText('€0.50 per unit');
  await expect(created).toContainText('All products');
  await expect(created).toContainText('Active');
  expect(psql(`select rule_type || ':' || amount || ':' || applies_to from pricing_discountrule where code = '${code}'`)).toBe(
    'fixed:50:products',
  );
});

test('PRICING-F11: «Edit» opens the rule with what it has and the row shows the change', async ({ page }) => {
  // flow: PRICING-F11
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const rule = await newRule(page, s, 'EDIT', { rule_type: 'percent', percent: '5' });
  await ready(page, RULES);
  await search(page, RULES, rule.code);
  await rowAction(page, RULES, rule.id, 'edit');
  const form = dialog(page, 'pricing-rule-form');
  await expect(form).toContainText(`Editing rule — ${rule.name}`);
  await expect(page.locator('[data-testid=pricing-rule-form-percent] input')).toHaveValue('5');
  await fill(page, 'pricing-rule-form-percent', '7,5');
  await fill(page, 'pricing-rule-form-priority', '40');
  await shootFlow(page, 'PRICING-F11');
  await page.locator('[data-testid=pricing-rule-form-submit]').click();
  await expect(form).toBeHidden();
  await expect(row(page, RULES, rule.code)).toContainText('7.5%');
  expect(psql(`select percent || '@' || priority from pricing_discountrule where id = '${rule.id}'`)).toBe('7.50@40');
});

test('PRICING-F12: «Deactivate» asks first; the rule waits under Inactive until «Activate»', async ({ page }) => {
  // flow: PRICING-F12
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const rule = await newRule(page, s, 'OFF', { rule_type: 'percent', percent: '20' });
  await ready(page, RULES);
  await search(page, RULES, rule.code);
  await rowAction(page, RULES, rule.id, 'deactivate');
  const confirm = dialog(page, 'pricing-rules-deactivate');
  await expect(confirm).toContainText(`${rule.name} will stop applying to new sales.`);
  await shootFlow(page, 'PRICING-F12');
  await page.locator('[data-testid=pricing-rules-deactivate-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(row(page, RULES, rule.code)).toHaveCount(0);

  await filterStatus(page, RULES, 'Inactive');
  await expect(row(page, RULES, rule.code)).toContainText('Inactive');
  await rowAction(page, RULES, rule.id, 'activate');
  await expect(row(page, RULES, rule.code)).toHaveCount(0);
  await filterStatus(page, RULES, 'Active');
  await expect(row(page, RULES, rule.code)).toContainText('Active');
  expect(psql(`select is_active from pricing_discountrule where id = '${rule.id}'`)).toBe('t');
});

// Price Lists, deleting a price list and a discount rule (apps/pricing/WORKBOOK.md), in Chrome against the real
// Inventory app, each flow with its screenshots at 390, 834 and 1440:
//   - PRICING-F16: «Delete» in the row's «⋮» asks first and the list goes with its prices, its code free again; from
//     its detail, the bin asks the same and goes back to Price Lists;
//   - PRICING-F17: «Delete» in the rule's «⋮» asks first and the rule goes, its code free again.
import { expect, test } from '@playwright/test';

import { A, login, psql } from './helpers';
import {
  cleanPricing,
  CODE,
  createProduct,
  DESKTOP,
  dialog,
  newList,
  newRule,
  post,
  ready,
  row,
  search,
  shootConfirm,
  shootFlow,
  stamp,
  TAG,
} from './pricing-helpers';
import { rowAction } from './service-helpers';

test.use({ viewport: DESKTOP, locale: 'en-US' });
test.beforeAll(cleanPricing);
test.afterAll(cleanPricing);

const LISTS = 'pricing-lists';
const RULES = 'pricing-rules';

test('PRICING-F16: «Delete» asks first and the list goes with its prices, from its row and from its detail', async ({ page }) => {
  // flow: PRICING-F16
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const list = await newList(page, s, 'GONE');
  const mask = await createProduct(page.context(), `${TAG} Mask ${s}`, `${CODE}-MSK${s}`, 900);
  await post(page.context(), '/pricing/price_items', { price_list_id: list.id, product_id: mask.id, price: 800 });
  await ready(page, LISTS);
  await search(page, LISTS, list.code);
  const confirm = dialog(page, 'pricing-list-delete');
  const ask = async () => {
    await rowAction(page, LISTS, list.id, 'delete');
    await expect(confirm).toContainText(`${list.name} disappears with all its prices. Sales already made do not change.`);
  };
  await shootConfirm(page, 'PRICING-F16', 'pricing-list-delete', ask);
  await ask();
  await page.locator('[data-testid=pricing-list-delete-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(row(page, LISTS, list.code)).toHaveCount(0);
  expect(psql(`select count(*) from pricing_priceitem where price_list_id = '${list.id}'`)).toBe('0');
  // Its code is free again: a new list takes it.
  const again = await post<{ id: string }>(page.context(), '/pricing/price_lists', { code: list.code, name: list.name });

  await page.goto(`${A}/pricing/lists/${again.id}`);
  await expect(page.locator('[data-testid=pricing-detail-summary]')).toBeVisible();
  await shootFlow(page, 'PRICING-F16-detail');
  await page.locator('[data-testid=pricing-detail-delete]').click();
  await expect(dialog(page, 'pricing-list-delete')).toContainText(`${list.name} disappears with all its prices.`);
  await page.locator('[data-testid=pricing-list-delete-submit]').click();
  await expect(page).toHaveURL(`${A}/pricing/lists`);
  expect(psql(`select count(*) from pricing_pricelist where id = '${again.id}'`)).toBe('0');
});

test('PRICING-F17: «Delete» asks first and the rule goes, its code free again', async ({ page }) => {
  // flow: PRICING-F17
  const s = stamp();
  await login(page, A, '/pricing/lists');
  const rule = await newRule(page, s, 'GONE', { rule_type: 'percent', percent: '15' });
  await ready(page, RULES);
  await search(page, RULES, rule.code);
  const confirm = dialog(page, 'pricing-rules-delete');
  const ask = async () => {
    await rowAction(page, RULES, rule.id, 'delete');
    await expect(confirm).toContainText(
      `${rule.name} disappears and stops applying to new sales. Sales already made do not change.`,
    );
  };
  await shootConfirm(page, 'PRICING-F17', 'pricing-rules-delete', ask);
  await ask();
  await page.locator('[data-testid=pricing-rules-delete-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(row(page, RULES, rule.code)).toHaveCount(0);
  expect(psql(`select count(*) from pricing_discountrule where id = '${rule.id}'`)).toBe('0');
  await post(page.context(), '/pricing/rules', { code: rule.code, name: rule.name, rule_type: 'percent', percent: '15' });
});

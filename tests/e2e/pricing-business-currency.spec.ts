// flow: pricing-business-currency
// Price Lists in the business's currency: its country's, as erplora.com registered it (`PUT /internal/hubs/{id}`,
// signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: «New price list» proposes PLN and
// the list is created in złoty (its Currency column says PLN); its detail reads its price and the catalog's in złoty
// and no «€», in 390, 834 and 1440 (captures `FIX-HUB-PRICING-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`), and it
// can be made general. Back in Spain «New price list» proposes EUR, the zloty list keeps its złoty (nothing stored is
// rewritten) and the catalog price reads in euros (`…-es-1440`). Editing an amount-per-unit rule in złoty (PRICING-F11)
// shows its amount in złoty and «Save» keeps it (captures `FIX-HUB-PRICING-MONEY-FIELD-OPENED-BEFORE-THE-BUSINESS-ANSWERS-
// <width>`; the business answering after the dialog opened is the race `RuleFormModal.test.ts` proves). The server
// prices a line (PRICING-F13) in złoty, the currency Pricing asks `base` for (captures `FIX-HUB-PRICING-OWN-COPY-OF-
// BUSINESS-CURRENCY-<width>`). What the run creates is deleted after it and `a`'s registration put back, also when a
// test fails.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { createProduct, dialog, post, ready, row, rowAction, search, stamp } from './pricing-helpers';
import { settled } from './service-helpers';

const KEY = 'FIX-HUB-PRICING-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const RULE_KEY = 'FIX-HUB-PRICING-MONEY-FIELD-OPENED-BEFORE-THE-BUSINESS-ANSWERS';
const LINE_KEY = 'FIX-HUB-PRICING-OWN-COPY-OF-BUSINESS-CURRENCY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const PREFIX = 'E2EPCUR';
const RUN = stamp();
const CODE = `${PREFIX}${RUN}`;
const SKU = `${PREFIX}-${RUN}`;
const PRODUCT = `E2E Pricing currency ${RUN} Shampoo`;
/** 12,50 and 15,00 as a business in Poland reads them: «12,50 zł», «zł 12.50». */
const ZLOTY_PRICE = /zł\s?12[.,]50|12[.,]50\s?zł/;
const ZLOTY_CATALOG = /zł\s?15[.,]00|15[.,]00\s?zł/;
const EURO_CATALOG = /€\s?15[.,]00|15[.,]00\s?€/;
/** 0,50 per unit as a business in Poland reads it. */
const ZLOTY_PER_UNIT = /(zł\s?0[.,]50|0[.,]50\s?zł) per unit/;

/** `a`'s registration as the run found it (put back after). */
let original: Registration;

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

function cleanUp(): void {
  const products = `select id from inventory_product where sku like '${PREFIX}-%'`;
  const lists = `select id from pricing_pricelist where code like '${PREFIX}%'`;
  psql(
    [
      `delete from pricing_priceitem where price_list_id in (${lists}) or product_id in (${products})`,
      `delete from pricing_pricelist where code like '${PREFIX}%'`,
      `delete from pricing_discountrule where code like '${PREFIX}%'`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      `delete from inventory_product where sku like '${PREFIX}-%'`,
    ].join('; '),
  );
}

/** The id of the run's list (made through the screen in the first test). */
const listId = (): string => psql(`select id from pricing_pricelist where code = '${CODE}'`);

/** The run's list in Price Lists → «Price lists», looked up by its code. */
async function listRow(page: Page) {
  await page.goto(`${A}/pricing/lists`);
  await ready(page, 'pricing-lists');
  await search(page, 'pricing-lists', CODE);
  const found = row(page, 'pricing-lists', CODE).first();
  await expect(found).toBeVisible();
  return found;
}

/** The run's product in the run's list's detail. */
async function itemRow(page: Page) {
  await page.goto(`${A}/pricing/lists/${listId()}`);
  await ready(page, 'pricing-items');
  const found = row(page, 'pricing-items', PRODUCT).first();
  await expect(found).toBeVisible();
  return found;
}

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  await registerBusinessIn(original, 'PL');
  const context = await browser.newContext({ baseURL: A, locale: 'en-US' });
  await login(await context.newPage(), A, '/pricing/lists');
  await createProduct(context, PRODUCT, SKU, 1500);
  await context.close();
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
});

test(`${KEY}: pricing-business-currency in Poland «New price list» proposes PLN and the list is created in złoty`, async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/pricing/lists');
  await ready(page, 'pricing-lists');
  await shown(page).locator('[data-testid=pricing-lists-add]').click();
  const form = dialog(page, 'pricing-list-form');
  await expect(form.locator('[data-testid=pricing-list-form-currency] input')).toHaveValue('PLN');
  await form.locator('[data-testid=pricing-list-form-code] input').fill(CODE);
  await form.locator('[data-testid=pricing-list-form-name] input').fill(`E2E Pricing currency ${RUN}`);
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-new-1440`) });
  await form.locator('[data-testid=pricing-list-form-submit]').click();
  await expect(form).toBeHidden();
  expect(psql(`select currency from pricing_pricelist where code = '${CODE}'`)).toBe('PLN');
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    const found = await listRow(page);
    await expect(found, size.name).toContainText('PLN');
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-lists-${size.name}`) });
  }
});

test(`${KEY}: pricing-business-currency in Poland a price list's detail reads its prices in złoty and no euro in 390, 834 and 1440`, async ({
  page,
  context,
}) => {
  await login(page, A, '/pricing/lists');
  const product = psql(`select id from inventory_product where sku = '${SKU}'`);
  await post(context, '/pricing/price_items', { price_list_id: listId(), product_id: product, price: 1250 });
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    const found = await itemRow(page);
    await expect(found, size.name).toContainText(ZLOTY_PRICE);
    await expect(found, size.name).not.toContainText('€');
    await expect(shown(page).locator('[data-testid=pricing-detail-summary]'), size.name).toContainText('PLN');
    await found.scrollIntoViewIfNeeded();
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
  }
  // The catalog price (a low-priority column, shown from the tablet on) is the business's too, and a list in the
  // business's currency, without a group, can be the general one (PRICING-F04; on a phone, inside «⋮»).
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(await itemRow(page)).toContainText(ZLOTY_CATALOG);
  await expect(shown(page).locator('[data-testid=pricing-detail-default]')).toBeVisible();
});

test(`${LINE_KEY}: PRICING-F13 in Poland the server prices a line in złoty, the currency base answers`, async ({
  page,
  context,
}) => {
  // flow: PRICING-F13
  // Pricing asks `base` for the business's currency (`base.operations.business_currency`, BASE-F50), never a copy of
  // its own: with `a` registered in Poland, a line without a list is the catalog's 15,00 in złoty, and one from the
  // run's list its 12,50 in złoty.
  await login(page, A, '/pricing/lists');
  type Line = { unit_price: number; price_list_code: string | null; currency: string; total: number };
  const catalog = await api<Line>(context, A, 'GET', `/pricing/prices/resolve?product=${encodeURIComponent(SKU)}`);
  expect(catalog.status, JSON.stringify(catalog.data)).toBe(200);
  expect(catalog.data).toMatchObject({ unit_price: 1500, price_list_code: null, currency: 'PLN', total: 1500 });
  const listed = await api<Line>(
    context,
    A,
    'GET',
    `/pricing/prices/resolve?product=${encodeURIComponent(SKU)}&price_list=${encodeURIComponent(CODE)}`,
  );
  expect(listed.status, JSON.stringify(listed.data)).toBe(200);
  expect(listed.data).toMatchObject({ unit_price: 1250, price_list_code: CODE, currency: 'PLN', total: 1250 });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    const found = await itemRow(page);
    await expect(found, size.name).toContainText(ZLOTY_PRICE);
    await expect(found, size.name).not.toContainText('€');
    await found.scrollIntoViewIfNeeded();
    await settled(page);
    await page.screenshot({ path: shot(`${LINE_KEY}-${size.name}`) });
  }
});

test(`${RULE_KEY}: PRICING-F11 editing an amount-per-unit rule in złoty shows it in złoty and «Save» keeps it`, async ({ page }) => {
  // flow: PRICING-F11
  await login(page, A, '/pricing/lists');
  const code = `${CODE}R`;
  const name = `E2E Pricing currency ${RUN} rule`;
  const made = await post<{ id: string }>(page.context(), '/pricing/rules', { code, name, rule_type: 'fixed', amount: 50, applies_to: 'all' });
  await page.setViewportSize({ width: 1440, height: 900 });
  await ready(page, 'pricing-rules');
  await search(page, 'pricing-rules', code);
  await expect(row(page, 'pricing-rules', code)).toContainText(ZLOTY_PER_UNIT);
  await rowAction(page, 'pricing-rules', made.id, 'edit');
  const form = dialog(page, 'pricing-rule-form');
  await expect(form).toContainText(`Editing rule — ${name}`);
  await expect(form.locator('[data-testid=pricing-rule-form-amount] input')).toHaveValue('0.50');
  await form.locator('[data-testid=pricing-rule-form-name] input').fill(`${name} edited`);
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await settled(page);
    await page.screenshot({ path: shot(`${RULE_KEY}-${size.name}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await form.locator('[data-testid=pricing-rule-form-submit]').click();
  await expect(form).toBeHidden();
  expect(psql(`select amount || '@' || name from pricing_discountrule where id = '${made.id}'`)).toBe(`50@${name} edited`);
  await expect(row(page, 'pricing-rules', code)).toContainText(ZLOTY_PER_UNIT);
});

test(`${KEY}: pricing-business-currency back in Spain «New price list» proposes EUR and the zloty list keeps its złoty`, async ({
  page,
}) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/pricing/lists');
  await ready(page, 'pricing-lists');
  await shown(page).locator('[data-testid=pricing-lists-add]').click();
  const form = dialog(page, 'pricing-list-form');
  await expect(form.locator('[data-testid=pricing-list-form-currency] input')).toHaveValue('EUR');
  await form.locator('[data-testid=pricing-list-form-cancel]').click();
  await expect(form).toBeHidden();
  const found = await itemRow(page);
  await expect(found).toContainText(ZLOTY_PRICE);
  await expect(found).toContainText(EURO_CATALOG);
  // The zloty list is no longer in the business's currency: it cannot be the general one.
  await expect(shown(page).locator('[data-testid=pricing-detail-default]')).toHaveCount(0);
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
});

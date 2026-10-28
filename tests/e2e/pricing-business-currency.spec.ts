// flow: pricing-business-currency
// Price Lists in the business's currency: its country's, as erplora.com registered it (`PUT /internal/hubs/{id}`,
// signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: «New price list» proposes PLN and
// the list is created in złoty (its Currency column says PLN); its detail reads its price and the catalog's in złoty
// and no «€», in 390, 834 and 1440 (captures `FIX-HUB-PRICING-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`), and it
// can be made general. Back in Spain «New price list» proposes EUR, the zloty list keeps its złoty (nothing stored is
// rewritten) and the catalog price reads in euros (`…-es-1440`). What the run creates is deleted after it and `a`'s
// registration put back, also when a test fails.
import { expect, type Page, test } from '@playwright/test';

import { A, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { createProduct, dialog, post, ready, row, search, stamp } from './pricing-helpers';
import { settled } from './service-helpers';

const KEY = 'FIX-HUB-PRICING-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
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

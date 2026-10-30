// flow: base-money-thousands-grouping — FIX-HUB-MONEY-THOUSANDS-SEPARATOR (hub#1090)
// The Hub writes an amount one way, its thousands grouped from four digits on: «1.234,56 €», never «1234,56 €» (the
// Spanish CLDR only groups from five). A sale of 1.234,56 € charged through Sales' API reads so in the Home's
// «Activity» (written with the platform's `formatMoney`, @erplora/ui/components), and a price of 1.234,56 € in a
// Price List's detail reads the same (Pricing groups on its own: looked at here, not touched), as the owner reads them
// in Spanish at 390, 834 and 1440. What the run creates is deleted after it, also when a test fails.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, psql, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { post, ready, row } from './pricing-helpers';
import { chargeByApi, cleanSales, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-MONEY-THOUSANDS-SEPARATOR';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const RUN = stamp();
/** Inventory's `cleanInventory()` takes every `E2E-…` product; the list's code is this run's own. */
const SKU = `E2E-MNYG-${RUN}`;
const PRODUCT = `E2E Thousands ${RUN}`;
const LIST_PREFIX = 'E2EMNYG';
const LIST_CODE = `${LIST_PREFIX}${RUN}`;
/** 1.234,56 € in its minor unit, as the server keeps every amount. */
const AMOUNT = 123456;
/** «1.234,56 €» as Intl paints it in Spanish (a no-break space before «€»). */
const GROUPED = /1\.234,56\s€/;
const UNGROUPED = /1234,56/;

let saleId = '';
let listId = '';

function cleanPricing(): void {
  const lists = `select id from pricing_pricelist where code like '${LIST_PREFIX}%'`;
  psql([`delete from pricing_priceitem where price_list_id in (${lists})`, `delete from pricing_pricelist where code like '${LIST_PREFIX}%'`].join('; '));
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/');
  const product = await createProduct(context, { name: PRODUCT, sku: SKU, price: AMOUNT, tax_category_key: 'product.generic' });
  const sale = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  expect(sale.total).toBe(AMOUNT);
  saleId = sale.id;
  // A list in the business's currency with the product at the same price (the catalog's also reads 1.234,56 €).
  const list = await post<{ id: string }>(context, '/pricing/price_lists', { code: LIST_CODE, name: `E2E Thousands ${RUN}` });
  listId = list.id;
  await post(context, '/pricing/price_items', { price_list_id: listId, product_id: product.id, price: AMOUNT });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanPricing();
    cleanSales();
  } finally {
    cleanInventory();
  }
});

/** The owner on `a` in Spanish: the Hub's language cookie, as the sign-in sets it from the account. */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  // From `/`, the address `/#actividad` only moves the hash: a full load reads the cookie (base-home-activity.spec.ts).
  await page.goto('about:blank');
  await page.goto(`${A}/#actividad`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

async function grouped(where: Locator): Promise<void> {
  await expect(where).toBeVisible();
  await expect(where).toContainText(GROUPED);
  await expect(where).not.toContainText(UNGROUPED);
}

for (const size of SIZES) {
  test(`base-money-thousands-grouping at ${size.label}: the Home's «Activity» and a Price List write 1.234,56 € with its thousands grouped`, async ({
    browser,
  }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      // The Home's «Activity» (base): the sale's row, by its id.
      await expect(shown(page).locator('[data-testid=home-activity-search]')).toBeVisible();
      const sale = shown(page).locator(`[data-testid=home-activity-row][data-id="${saleId}"]`);
      await grouped(sale);
      await sale.scrollIntoViewIfNeeded();
      await capture(page, `${KEY}-${size.label}`);

      // Price Lists (Pricing, which already groups): the product's row in the run's list.
      await page.goto(`${A}/pricing/lists/${listId}`);
      await ready(page, 'pricing-items');
      const item = row(page, 'pricing-items', PRODUCT).first();
      await grouped(item);
      await item.scrollIntoViewIfNeeded();
      await capture(page, `${KEY}-pricing-${size.label}`);
    } finally {
      await context.close();
    }
  });
}

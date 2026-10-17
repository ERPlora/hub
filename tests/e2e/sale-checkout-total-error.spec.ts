// The charge sheet when the server cannot work out the total (FIX-SALE-CHECKOUT-TOTAL-SPINNER): a product
// whose tax category has no rule in the business's country is on the check and «Charge» is tapped. The sheet
// says why, in the server's words, with «Retry», and the error replaces «Working out the total…» — never both
// at once (Square, Shopify POS, Toast). «Retry» asks the server again and, with the rule still missing, the
// error comes back alone. Seen at 390×844, 834×1112 and 1440×900 (`FIX-SALE-CHECKOUT-TOTAL-SPINNER-<width>.png`).
// What the run makes is deleted after it.
// flow: ninguno — FIX sale
import { expect, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, stamp } from './sale-helpers';
import { cleanUp as cleanTaxes, FLOW_VIEWPORTS, freshCategory } from './tax-helpers';

const RUN = stamp();
let orphan: Product;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // A category of this run with no rule at all: nothing says how it is taxed here.
  const key = await freshCategory(context, 'norule');
  orphan = await createProduct(context, { name: `E2E No rule ${RUN}`, sku: `E2E-NORULE-${RUN}`, price: 500, tax_category_key: key });
  await context.close();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
  cleanTaxes();
});

test('ninguno — FIX sale: a total the server cannot work out shows its error with «Retry», never «Working out the total…» with it', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(orphan.sku);
  await search.locator(`[data-testid=pos-search-${orphan.id}]`).click();
  await shown(page).locator('[data-testid=pos-charge]').click();

  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  const error = sheet.locator('[data-testid=sale-checkout-read-error]');
  await expect(error).toBeVisible();
  await expect(error).toContainText(orphan.name);
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toHaveCount(0);
  await expect(sheet.locator('ion-spinner')).toHaveCount(0);
  await expect(sheet.locator('[data-testid=sale-checkout-confirm]')).toHaveAttribute('aria-disabled', 'true');

  // «Retry» reopens the live stream (the server runs the total again); still no rule: the error, alone.
  const asked = page.waitForRequest((request) => new URL(request.url()).pathname === '/api/live');
  await sheet.locator('[data-testid=sale-checkout-retry]').click();
  await asked;
  await expect(error).toBeVisible();
  await expect(error).toContainText(orphan.name);
  await expect(sheet.locator('ion-spinner')).toHaveCount(0);

  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(error).toBeInViewport();
    await expect(sheet.locator('[data-testid=sale-checkout-retry]')).toBeInViewport();
    await expect(sheet.locator('ion-spinner')).toHaveCount(0);
    await page.screenshot({ path: shot(`FIX-SALE-CHECKOUT-TOTAL-SPINNER-${vp.label}`) });
  }
});

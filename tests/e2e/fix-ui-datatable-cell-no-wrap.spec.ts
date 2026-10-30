// flow: ui-datatable-cell-no-wrap
// Inventory → Products in Chrome (FIX-UI-DATATABLE-CELL-NO-WRAP-SQUEEZES-CHIP-BESIDE-BADGE): a product whose tax
// category Taxes deactivated («Not configured») and that is also sold out paints the chip and the «Sold out» badge
// in the same Status cell. Where the row has no room for both, the badge drops under the chip (Shopify, Odoo and
// Square stack status badges when the column is short of them) instead of squeezing the chip to its corner: the
// chip stays whole or as wide as its cell, its icon in sight and its text whole or ending in «…», and the badge
// whole, inside the cell and never over the chip, at 390 (cards), 820, 834 and 1440.
import { expect, test } from '@playwright/test';

import { A, api, capture, login, psql, record, shown } from './helpers';
import { chipBesideBadge, chipFit, cleanInventory, createProduct, type Product, productsReady, settled, stamp } from './inventory-helpers';

test.afterAll(() => {
  cleanInventory();
});

const KEY = 'FIX-UI-DATATABLE-CELL-NO-WRAP-SQUEEZES-CHIP-BESIDE-BADGE';

/** A phone (cards), the two tablets the report measured and a desk. */
const WIDTHS = [
  { label: '390', width: 390, height: 844 },
  { label: '820', width: 820, height: 1180 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

test('FIX-UI-DATATABLE-CELL-NO-WRAP-SQUEEZES-CHIP-BESIDE-BADGE · ui-datatable-cell-no-wrap: a «Not configured» product that is sold out shows its chip and its «Sold out» badge whole, the badge under the chip when the row has no room', async ({
  page,
  context,
}) => {
  await login(page, A, '/inventory/dashboard');
  const key = `e2e.inv_wrap_${stamp().toLowerCase()}`;
  const created = await api(context, A, 'POST', '/tax/categories', { key, name: 'E2E wrap tax' });
  expect(created.status).toBe(201);
  const product = await createProduct(context, { name: 'E2E Wrap wine', sku: `E2E-WRAP-${stamp()}`, tax_category_key: key });
  const sold = await api<Product>(context, A, 'POST', '/inventory/products/sold_out', { id: product.id, sold_out: true });
  expect([sold.status, sold.data.is_sold_out]).toEqual([200, true]);
  // Taxes deactivates it (there is no screen for it yet): the product is «Not configured».
  psql(`update tax_taxcategory set is_active = false where key = '${key}'`);
  try {
    await page.goto(`${A}/inventory/products?status=unconfigured`);
    await productsReady(page);
    // The session, for ui-clip-sweep.sh over this same page.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    const chip = shown(page).locator(`[data-testid=inventory-products-unconfigured-${product.id}]`);
    const badge = `[data-testid=inventory-products-sold-out-${product.id}]`;
    const within = '[role=cell], .data-table__field-value';
    for (const vp of WIDTHS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(chip).toBeVisible();
      await expect(shown(page).locator(badge)).toBeVisible();
      const fit = await settled(
        async () => {
          const alone = await chipFit(chip, { within, titled: true });
          const pair = await chipBesideBadge(chip, { within, badge });
          return { problems: [...alone.problems, ...pair.problems], metrics: { ...alone.metrics, ...pair.metrics } };
        },
        `list at ${vp.label}`,
        { problems: [], metrics: {} },
      );
      record(`${KEY}-${vp.label}`, { ...fit.metrics, problems: fit.problems });
      await capture(page, `${KEY}-${vp.label}`);
    }
  } finally {
    psql(`update tax_taxcategory set is_active = true where key = '${key}'`);
  }
});

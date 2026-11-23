// flow: INVENTORY-F02 — «Editing product» opened while the tab's live stream cannot open (a proxy's 502 page, what a Hub
// that is restarting answers). «Tax category» and «Categories» said nothing: the first looked empty and the second was
// not there, as if the product had neither. Now each says its read failed, with the reason, and once the stream opens
// again by itself both show what the product has saved. The stream is answered 502 in the browser (`page.route`) only
// after the list has loaded; nothing is saved.
import { writeFileSync } from 'node:fs';

import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, login } from './helpers';
import { cleanInventory, createProduct, presentedDialog, productsReady, searchProducts, stamp } from './inventory-helpers';
import { rowAction } from './service-helpers';

const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
];
const LIVE = '**/api/live?**';

test.afterAll(() => {
  cleanInventory();
});

async function badGateway(page: Page): Promise<void> {
  await page.route(LIVE, (route) =>
    route.fulfill({ status: 502, contentType: 'text/html', body: '<html><body><h1>502 Bad Gateway</h1></body></html>' }),
  );
}

for (const size of SIZES) {
  const label = `${size.width}x${size.height}`;
  test(`INVENTORY-F02 ${label}: a stream that cannot open says so in «Tax category» and «Categories», and what is saved comes back with it`, async ({
    page,
    context,
  }) => {
    await page.setViewportSize(size);
    await login(page, A);
    const sku = `E2E-READS-${stamp()}`;
    const shelf = await api<{ id: string }>(context, A, 'POST', '/inventory/categories', { name: `E2E Desserts ${sku}` });
    expect(shelf.status, 'create the category').toBe(201);
    const tart = await createProduct(context, { name: 'E2E Cheesecake', sku, price: 450, category_ids: [shelf.data.id] });
    await page.goto('/inventory/products');
    await productsReady(page);
    await searchProducts(page, sku);

    await badGateway(page);
    const form = await presentedDialog(page, 'inventory-product-form', () => rowAction(page, 'inventory-products', tart.id, 'edit'));
    await expect(form.locator('[data-testid=inventory-product-tax-error]')).toContainText(
      /The tax categories could not be loaded|No se pudieron cargar las categorías fiscales/,
    );
    await expect(form.locator('[data-testid=inventory-product-categories-error]')).toContainText(
      /The categories could not be loaded|No se pudieron cargar las categorías/,
    );
    await expect(form.locator('[data-testid=inventory-product-tax-unconfigured]')).toHaveCount(0);
    // Both notices on screen for the capture: the panel scrolls, and they sit below the amounts.
    await form.locator('[data-testid=inventory-product-tax-error]').evaluate((notice) => notice.scrollIntoView({ block: 'center' }));
    const png = await capture(page, `INVENTORY-F02-failed-reads-${label}`);
    writeFileSync(test.info().outputPath(`INVENTORY-F02-failed-reads-${label}.png`), png);

    await page.unroute(LIVE);
    await expect(form.locator(`[data-testid=inventory-product-categories-chip-${shelf.data.id}]`)).toContainText(`E2E Desserts ${sku}`, {
      timeout: 45_000,
    });
    await expect(form.locator('[data-testid=inventory-product-tax-error]')).toHaveCount(0);
    await expect(form.locator('[data-testid=inventory-product-categories-error]')).toHaveCount(0);
    const back = await capture(page, `INVENTORY-F02-reads-back-${label}`);
    writeFileSync(test.info().outputPath(`INVENTORY-F02-reads-back-${label}.png`), back);
  });
}

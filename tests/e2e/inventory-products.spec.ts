// Inventory → Products in Chrome against the real Taxes app (apps/inventory/WORKBOOK.md):
//   - INVENTORY-F01: «+» → «New product», the tax category picked among those Taxes seeds; the
//     product arrives live, active, not «Not configured»; the field a person went to while the form was opening
//     keeps what they type (hub#700);
//   - the form's refusals under their field: 422 (a price over the limit) and 409 (a SKU taken);
//   - INVENTORY-F05: a product whose tax category Taxes deactivated is «Not configured», the sale
//     catalog says it cannot be sold, and saving it with that category is refused; picking another
//     one in the form fixes it; its «Not configured» chip keeps its icon in sight and its text whole while the
//     row has room, or ending in «…» with the whole text as its title, at 390, 834, 1280 and 1440, in English and
//     in Spanish;
//   - INVENTORY-F11: the export downloads the filtered catalog with the headers the import reads;
//   - `/inventory` lands on the dashboard and the tabs walk the five sections; screenshots of every page in three
//     viewports;
//   - the list filters behind the table's funnel (price in euros), with its count, at every width; an
//     amount it cannot read is said under its field and does not filter.
import { expect, test } from '@playwright/test';

import { A, api, capture, login, psql, record, shot, shown } from './helpers';
import {
  cleanInventory,
  createProduct,
  dialog,
  fill,
  GENERIC,
  pickCombo,
  productBySku,
  productRow,
  productsReady,
  searchProducts,
  settledChipFit,
  shoot,
  shootFlow,
  stamp,
} from './inventory-helpers';
import { rowAction } from './service-helpers';

test.afterAll(() => {
  cleanInventory();
});

/** The widths of the filter panel's screenshots: a phone (the panel is a sheet), a tablet and a desk
 *  (two columns), as the SaaS panel's `VIEWPORTS`. */
const FILTER_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

test('INVENTORY-F01: a new product with a tax category of Taxes arrives live, active and configured', async ({ page, context }) => {
  const sku = `E2E-NEW-${stamp()}`;
  await login(page, A, '/inventory/products');
  await productsReady(page);

  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await expect(form).toBeVisible();
  await expect(form.locator('[data-testid=inventory-product-form-submit]')).toHaveJSProperty('disabled', true);
  await expect(form.locator('[data-testid=inventory-product-name] input')).toBeFocused();
  await fill(form, 'inventory-product-name', 'E2E Coffee');
  await fill(form, 'inventory-product-sku', sku);
  await fill(form, 'inventory-product-price', '2,20');
  await fill(form, 'inventory-product-initial-stock', '5');
  // The picker offers what Taxes seeds, by name and rate («Product — generic · 21%»).
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general).*21/);
  await page.screenshot({ path: shot('inventory-product-new-1280') });
  await shootFlow(page, 'INVENTORY-F01');
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();

  await searchProducts(page, sku);
  const row = productRow(page, sku);
  await expect(row).toBeVisible();
  await expect(row.locator('ion-toggle')).toHaveCount(1);
  await expect(shown(page).locator('[data-testid^=inventory-products-unconfigured-]')).toHaveCount(0);
  const saved = await productBySku(context, sku);
  expect([saved.tax_category_key, saved.needs_tax_setup, saved.is_active, saved.stock]).toEqual([GENERIC, false, true, '5.000']);
});

test('INVENTORY-F01: the field a person went to while the form was opening keeps what they type, and «Save» lights up', async ({ page, context }) => {
  // hub#700: the dialog says it has opened about half a second after it shows. A person who is already in the SKU by
  // then stays there; before, the cursor jumped to the name, the text went there and the SKU stayed empty, with «Save» off.
  const sku = `E2E-OPENING-${stamp()}`;
  await page.setViewportSize({ width: 834, height: 1112 });
  await login(page, A, '/inventory/products');
  await productsReady(page);

  // Inside the page, frame by frame: from outside the first moment the field can take the focus would be a coin toss.
  const opened = page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const form = 'ion-modal[data-testid=inventory-product-form]';
        document.addEventListener(
          'didPresent',
          (event) => {
            if ((event.target as Element).matches(form)) resolve();
          },
          { capture: true },
        );
        const goToSku = () => {
          const input = document.querySelector<HTMLInputElement>(`${form} [data-testid=inventory-product-sku] input`);
          input?.focus();
          if (!input || document.activeElement !== input) requestAnimationFrame(goToSku);
        };
        requestAnimationFrame(goToSku);
      }),
  );
  await shown(page).locator('[data-testid=inventory-products-add]').click();
  await opened;

  const form = dialog(page, 'inventory-product-form');
  const skuInput = form.locator('[data-testid=inventory-product-sku] input');
  await expect(skuInput).toBeFocused();
  await page.keyboard.type(sku);
  await expect(skuInput).toHaveValue(sku);
  await expect(form.locator('[data-testid=inventory-product-name] input')).toHaveValue('');

  await fill(form, 'inventory-product-name', 'E2E Opening');
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general).*21/);
  const save = form.locator('[data-testid=inventory-product-form-submit]');
  await expect(save).toHaveJSProperty('disabled', false);
  await save.click();
  await expect(form).toBeHidden();
  const saved = await productBySku(context, sku);
  expect([saved.name, saved.tax_category_key]).toEqual(['E2E Opening', GENERIC]);
});

test('selectores de Inventario (Combo compartido): the product form searches its tax category and its categories on the server, at every width', async ({
  page,
  context,
}) => {
  // flow: selectores de Inventario (Combo compartido) — INVENTORY-F01, INVENTORY-F08
  await login(page, A, '/inventory/products');
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  const category = async (name: string) => {
    const res = await api<{ id: string; name: string }>(context, A, 'POST', '/inventory/categories', { name });
    expect(res.status).toBe(201);
    return res.data;
  };
  const drinks = await category(`E2E Combo drinks ${stamp()}`);
  const food = await category(`E2E Combo food ${stamp()}`);
  for (const { label, width, height } of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width, height });
    const sku = `E2E-COMBO-${label}-${stamp()}`;
    await page.goto(`${A}/inventory/products`);
    await productsReady(page);
    await shown(page).locator('[data-testid=inventory-products-add]').click();
    const form = dialog(page, 'inventory-product-form');
    await fill(form, 'inventory-product-name', `E2E Combo ${label}`);
    await fill(form, 'inventory-product-sku', sku);
    await fill(form, 'inventory-product-price', '1');
    await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general).*21/);
    await expect(form.locator('[data-testid=inventory-product-tax] input')).toHaveValue(/(Product — generic|Producto — general).*21/);

    // «Categories»: each one found by typing and added under the field as a chip.
    const categories = form.locator('[data-testid=inventory-product-categories]');
    await pickCombo(page, categories, drinks.name, drinks.name);
    await categories.locator('input').fill(food.name);
    const offered = page.locator('[data-testid^="inventory-product-categories-option-"]');
    await expect(offered).toHaveText([food.name]);
    await offered.first().click();
    const chips = form.locator('[data-testid^="inventory-product-categories-chip-"]');
    await expect(chips).toHaveText([drinks.name, food.name]);
    await expect(offered).toHaveCount(0);
    await chips.last().scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot(`FIX-INVENTORY-SEARCHSELECT-TO-COMBO-${label}`) });

    // A chosen category is not offered again; the button of its chip takes it away.
    await categories.locator('input').fill(drinks.name);
    await expect(page.locator('[data-testid=inventory-product-categories-empty]')).toBeVisible();
    await expect(offered).toHaveCount(0);
    await categories.locator('input').press('Escape');
    await expect(form).toBeVisible();
    await form.locator(`[data-testid=inventory-product-categories-remove-${drinks.id}]`).click();
    await expect(chips).toHaveText([food.name]);

    await form.locator('[data-testid=inventory-product-form-submit]').click();
    await expect(form).toBeHidden();
    const saved = await productBySku(context, sku);
    expect([saved.tax_category_key, saved.category_ids]).toEqual([GENERIC, [food.id]]);
  }
});

test('the form keeps a refusal under its field: 422 for a price over the limit, 409 for a SKU taken', async ({ page, context }) => {
  await login(page, A, '/inventory/products');
  await productsReady(page);
  const taken = await createProduct(context, { name: 'E2E Taken', sku: `E2E-TAKEN-${stamp()}` });

  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await fill(form, 'inventory-product-name', 'E2E Too dear');
  await fill(form, 'inventory-product-sku', `E2E-DEAR-${stamp()}`);
  await fill(form, 'inventory-product-price', '99999999999999');
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general)/);
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  const price = form.locator('[data-testid=inventory-product-price]');
  await expect(price).toHaveClass(/ion-invalid/);
  await expect(price.locator('.error-text')).not.toBeEmpty();
  await expect(form).toBeVisible();
  await page.screenshot({ path: shot('inventory-product-422-1280') });

  await fill(form, 'inventory-product-price', '3');
  await fill(form, 'inventory-product-sku', taken.sku);
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  const skuField = form.locator('[data-testid=inventory-product-sku]');
  await expect(skuField.locator('.error-text')).toContainText(/SKU/);
  await expect(form.locator('[data-testid=inventory-product-form-error]')).toBeVisible();
  await page.screenshot({ path: shot('inventory-product-409-1280') });
});

test('INVENTORY-F05: a product whose tax category Taxes deactivated is «Not configured», cannot be sold, and is fixed in its form', async ({ page, context }) => {
  await login(page, A, '/inventory/dashboard');
  const key = `e2e.inv_${stamp().toLowerCase()}`;
  const created = await api(context, A, 'POST', '/tax/categories', { key, name: 'E2E inventory tax' });
  expect(created.status).toBe(201);
  const sku = `E2E-UNSET-${stamp()}`;
  const product = await createProduct(context, { name: 'E2E Old wine', sku, tax_category_key: key });
  // Taxes deactivates it (there is no screen for it yet): the product cannot be sold any more.
  psql(`update tax_taxcategory set is_active = false where key = '${key}'`);
  try {
    const forSale = await api<{ rows: Array<{ id: string; needs_tax_setup: boolean }> }>(context, A, 'GET', `/inventory/products/for_sale?search=${sku}`);
    expect(forSale.data.rows.find((row) => row.id === product.id)?.needs_tax_setup).toBe(true);
    // Saving it with that category is refused, by the API as by the form.
    const refused = await api<{ error: { code: string; fields?: Record<string, string> } }>(context, A, 'POST', '/inventory/products/update', {
      id: product.id,
      tax_category_key: key,
    });
    expect(refused.status).toBe(422);
    expect(Object.keys(refused.data.error.fields ?? {})).toContain('tax_category_key');

    await page.goto(`${A}/inventory/products?status=unconfigured`);
    await productsReady(page);
    const marker = shown(page).locator(`[data-testid=inventory-products-unconfigured-${product.id}]`);
    await expect(marker).toBeVisible();
    await expect(marker).toContainText(/Not configured|Sin configurar/);
    await page.screenshot({ path: shot('inventory-products-unconfigured-1280') });
    await shootFlow(page, 'INVENTORY-F05');

    await marker.click();
    const form = dialog(page, 'inventory-product-form');
    await expect(form.locator('[data-testid=inventory-product-tax-unconfigured]')).toBeVisible();
    await expect(form.locator('[data-testid=inventory-product-form-submit]')).toHaveJSProperty('disabled', true);
    await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general)/);
    await form.locator('[data-testid=inventory-product-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(marker).toHaveCount(0);
    await expect.poll(async () => (await productBySku(context, sku)).needs_tax_setup).toBe(false);
  } finally {
    psql(`update tax_taxcategory set is_active = true where key = '${key}'`);
  }
});

/** The widths of the «Not configured» chip check: a phone (cards), a tablet, the old report's 1280 and a desk
 *  (`roomy`: the row has room for the whole chip). */
const CHIP_VIEWPORTS = [
  { label: '390', width: 390, height: 844, roomy: false },
  { label: '820', width: 820, height: 1180, roomy: false },
  { label: '834', width: 834, height: 1112, roomy: false },
  { label: '1280', width: 1280, height: 800, roomy: true },
  { label: '1440', width: 1440, height: 900, roomy: true },
];

// flow: INVENTORY-F05 (the «Not configured» chip of Products)
test('INVENTORY-F05: the «Not configured» chip keeps its icon in sight and reads those words, whole or ending in «…», at every width', async ({
  page,
  context,
  browser,
}) => {
  await login(page, A, '/inventory/dashboard');
  const key = `e2e.chip_${stamp().toLowerCase()}`;
  const created = await api(context, A, 'POST', '/tax/categories', { key, name: 'E2E chip tax' });
  expect(created.status).toBe(201);
  const product = await createProduct(context, { name: 'E2E Chip wine', sku: `E2E-CHIP-${stamp()}`, tax_category_key: key });
  psql(`update tax_taxcategory set is_active = false where key = '${key}'`);
  try {
    await page.goto(`${A}/inventory/products?status=unconfigured`);
    await productsReady(page);
    // The session, for ui-clip-sweep.sh over this same page.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    const marker = shown(page).locator(`[data-testid=inventory-products-unconfigured-${product.id}]`);
    // Soft checks: one run says what is wrong at every width.
    for (const vp of CHIP_VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(marker).toBeVisible();
      const options = { within: '[role=cell], .data-table__field-value', whole: vp.roomy, reads: 'Not configured', titled: true };
      const fit = await settledChipFit(marker, options, `list at ${vp.label}`);
      record(`FIX-INVENTORY-PRODUCTS-UNCONFIGURED-CHIP-CLIPPED-${vp.label}`, { ...fit.metrics, problems: fit.problems });
      await page.screenshot({ path: shot(`FIX-INVENTORY-PRODUCTS-UNCONFIGURED-CHIP-CLIPPED-${vp.label}`) });
    }

    // Tapping it still opens the form, whose own chip fits its field the same way.
    await marker.click();
    const form = dialog(page, 'inventory-product-form');
    const formChip = form.locator('[data-testid=inventory-product-tax-unconfigured]');
    await expect(formChip).toBeVisible();
    for (const vp of CHIP_VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await settledChipFit(formChip, { within: '.tax-category-select' }, `form at ${vp.label}`);
    }

    // hub#530: the business sees it in Spanish, «Sin configurar · Falta la categoría fiscal», wider than the English
    // one: whole at 1280 too, beside the «Photo» column (INVENTORY-F32). The Hub's language cookie, as the sign-in
    // sets it from the account.
    const spanish = await browser.newContext({ baseURL: A, viewport: { width: 1280, height: 800 }, locale: 'es-ES' });
    try {
      const es = await spanish.newPage();
      await login(es, A, '/inventory/dashboard');
      await spanish.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
      await es.goto(`${A}/inventory/products?status=unconfigured`);
      await expect(es.locator('html')).toHaveAttribute('lang', /^es/);
      await productsReady(es);
      const chip = shown(es).locator(`[data-testid=inventory-products-unconfigured-${product.id}]`);
      await expect(chip).toContainText('Sin configurar · Falta la categoría fiscal');
      for (const vp of CHIP_VIEWPORTS) {
        await es.setViewportSize({ width: vp.width, height: vp.height });
        await expect(chip).toBeVisible();
        const options = { within: '[role=cell], .data-table__field-value', whole: vp.roomy, reads: 'Sin configurar', titled: true };
        const fit = await settledChipFit(chip, options, `Spanish list at ${vp.label}`);
        record(`FIX-INVENTORY-PRODUCTS-UNCONFIGURED-CHIP-CLIPPED-es-${vp.label}`, { ...fit.metrics, problems: fit.problems });
        await capture(es, `FIX-INVENTORY-PRODUCTS-UNCONFIGURED-CHIP-CLIPPED-es-${vp.label}`);
      }
    } finally {
      await spanish.close();
    }
  } finally {
    psql(`update tax_taxcategory set is_active = true where key = '${key}'`);
  }
});

/** The tablets of hub#703: upright, whose row is the shortest of room while it stays a list, and on their side, where
 *  the side menu takes its part of the width. */
const TABLET_VIEWPORTS = [
  { label: '820', width: 820, height: 1180 },
  { label: '834', width: 834, height: 1112 },
  { label: '1024', width: 1024, height: 768 },
  { label: '1180', width: 1180, height: 820 },
];

// flow: INVENTORY-F05 (chip «Sin configurar» de Productos, en la tableta)
test('INVENTORY-F05 · hub#703: on a tablet the «Not configured» chip reads its words beside a long name, and the list keeps to its box', async ({
  page,
  context,
  browser,
}) => {
  await login(page, A, '/inventory/dashboard');
  const key = `e2e.tablet_${stamp().toLowerCase()}`;
  const created = await api(context, A, 'POST', '/tax/categories', { key, name: 'E2E tablet chip tax' });
  expect(created.status).toBe(201);
  const long = await createProduct(context, { name: 'Croquetas caseras de jamón ibérico', sku: `E2E-TABLET-${stamp()}`, tax_category_key: key });
  await createProduct(context, { name: 'E2E Tablet wine', sku: `E2E-TABLET-2-${stamp()}`, tax_category_key: key });
  psql(`update tax_taxcategory set is_active = false where key = '${key}'`);
  try {
    const languages = [
      { code: 'en', locale: 'en-GB', reads: 'Not configured' },
      { code: 'es', locale: 'es-ES', reads: 'Sin configurar' },
    ];
    for (const language of languages) {
      const own = await browser.newContext({ baseURL: A, viewport: { width: 820, height: 1180 }, locale: language.locale });
      try {
        const tablet = await own.newPage();
        await login(tablet, A, '/inventory/dashboard');
        await own.addCookies([{ name: 'django_language', value: language.code, domain: new URL(A).hostname, path: '/' }]);
        await tablet.goto(`${A}/inventory/products?status=unconfigured`);
        await expect(tablet.locator('html')).toHaveAttribute('lang', new RegExp(`^${language.code}`));
        await productsReady(tablet);
        // The session, for ui-clip-sweep.sh over this same page.
        if (process.env.E2E_SAVE_STORAGE_STATE) await own.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
        const chip = shown(tablet).locator(`[data-testid=inventory-products-unconfigured-${long.id}]`);
        for (const vp of TABLET_VIEWPORTS) {
          await tablet.setViewportSize({ width: vp.width, height: vp.height });
          await expect(chip).toBeVisible();
          const options = { within: '[role=cell]', reads: language.reads, titled: true };
          const fit = await settledChipFit(chip, options, `${language.code} list at ${vp.label}`);
          record(`hub-703-chip-${language.code}-${vp.label}`, { ...fit.metrics, problems: fit.problems });
          const scroll = shown(tablet).locator('.data-table__scroll').first();
          await expect.soft(scroll.evaluate((el) => el.scrollWidth - el.clientWidth), `${language.code} list at ${vp.label} keeps to its box`).resolves.toBeLessThanOrEqual(0);
          await capture(tablet, `hub-703-chip-${language.code}-${vp.label}`);
        }
      } finally {
        await own.close();
      }
    }

    // The mark gone, its room goes with it: the row's actions come back out of «⋮».
    psql(`update tax_taxcategory set is_active = true where key = '${key}'`);
    await page.setViewportSize({ width: 820, height: 1180 });
    await page.goto(`${A}/inventory/products`);
    await productsReady(page);
    await searchProducts(page, long.sku);
    await expect(shown(page).locator(`[data-testid=inventory-products-row-${long.id}-receive]`)).toBeVisible();
  } finally {
    psql(`update tax_taxcategory set is_active = true where key = '${key}'`);
  }
});

test('INVENTORY-F11: the export downloads what the search finds, with the headers the import reads', async ({ page, context }) => {
  const sku = `E2E-EXP-${stamp()}`;
  await login(page, A, '/inventory/products');
  await productsReady(page);
  await createProduct(context, { name: 'E2E Exported', sku, price: 220 });
  await searchProducts(page, sku);
  // The search is the server's (debounced): wait until the list holds only what it finds.
  await expect(shown(page).locator('[data-testid=inventory-products-row]')).toHaveCount(1);
  await expect(productRow(page, sku)).toBeVisible();
  await shootFlow(page, 'INVENTORY-F11');
  const [download] = await Promise.all([page.waitForEvent('download'), shown(page).locator('[data-testid=inventory-products-csv-export]').click()]);
  expect(download.suggestedFilename()).toMatch(/^inventor(y|io)-product(s|os)\.csv$/);
  const path = await download.path();
  const { readFileSync } = await import('node:fs');
  const text = readFileSync(path, 'utf8');
  const [header, ...lines] = text.replace(/^﻿/, '').trim().split(/\r?\n/);
  expect(header).toMatch(/^(Name|Nombre)[;,]SKU[;,]/);
  expect(lines).toHaveLength(1);
  expect(lines[0]).toContain(sku);
});

test('the tabs walk the five sections, each on its address; screenshots of every page in three viewports', async ({ page }) => {
  // `/inventory` is no page: the SPA's router sends it to the dashboard. `login` lands on a page (it timed out here
  // with a session kept by the tests above), so the walk signs
  // in on another tab and then asks for `/inventory`, as a person who types it.
  await login(page, A, '/inventory/settings');
  await page.goto(`${A}/inventory`);
  await page.waitForURL(/\/inventory\/dashboard$/);
  await shown(page).locator('[data-testid=inventory-dashboard-kpi-tracked]').waitFor();
  const shots: string[] = [];
  shots.push(...(await shoot(page, 'inventory-dashboard')));
  for (const [tab, path, ready] of [
    ['products', '/inventory/products', '[data-testid=inventory-products-row], [data-testid=inventory-products-empty]'],
    ['movements', '/inventory/movements', '[data-testid=inventory-movements-row], .data-table__empty'],
    ['categories', '/inventory/categories', '[data-testid=inventory-categories-row], [data-testid=inventory-categories-empty]'],
    ['settings', '/inventory/settings', '[data-testid=inventory-settings-form]'],
  ] as const) {
    await shown(page).locator(`[data-testid=tab-${tab}]`).click();
    await page.waitForURL(new RegExp(`${path}$`));
    await shown(page).locator(ready).first().waitFor({ state: 'visible' });
    shots.push(...(await shoot(page, `inventory-${tab}`)));
  }
  await shown(page).locator('[data-testid=tab-dashboard]').click();
  await page.waitForURL(/\/inventory\/dashboard$/);
  expect(shots).toHaveLength(15);
});

// flow: none — the column filters sit behind the table's funnel.
test('Products filter by price in euros behind the funnel, with its count; an amount it cannot read is said under it', async ({ page, context }) => {
  const run = stamp();
  await login(page, A, '/inventory/products');
  // 2,20 € and 15,00 €: «Price from 10» is ten euros (inventory#115), never ten cents.
  const cheap = await createProduct(context, { name: `E2E Cheap ${run}`, sku: `E2E-FIL-C-${run}`, price: 220 });
  const dear = await createProduct(context, { name: `E2E Dear ${run}`, sku: `E2E-FIL-D-${run}`, price: 1500 });
  const panel = shown(page).locator('[data-testid=inventory-products-filters-panel]');
  const toggle = shown(page).locator('[data-testid=inventory-products-filters-toggle]');
  const count = shown(page).locator('[data-testid=inventory-products-filters-count]');
  const priceFrom = panel.locator('[data-testid=inventory-products-filter-price_min]');
  for (const vp of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/inventory/products`);
    await productsReady(page);
    await searchProducts(page, run);
    await expect(productRow(page, cheap.sku)).toBeVisible();
    await expect(productRow(page, dear.sku)).toBeVisible();
    await toggle.click();
    await expect(panel).toBeVisible();
    await priceFrom.locator('input').fill('10');
    await panel.locator('[data-testid=inventory-products-filters-apply]').click();
    await expect(panel).toBeHidden();
    await expect(count).toHaveText('1');
    await expect(productRow(page, dear.sku)).toBeVisible();
    await expect(productRow(page, cheap.sku)).toHaveCount(0);
    await toggle.click();
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-FILTERS-2A-inventory-${vp.label}`) });
    await panel.locator('[data-testid=inventory-products-filters-clear]').click();
    await expect(count).toHaveCount(0);
    await panel.locator('[data-testid=inventory-products-filters-close]').click();
    await expect(panel).toBeHidden();
    await expect(productRow(page, cheap.sku)).toBeVisible();
  }

  // «doce» is not an amount: said under «Price from», the funnel turns red, and nothing is filtered.
  await toggle.click();
  await priceFrom.locator('input').fill('doce');
  await panel.locator('[data-testid=inventory-products-filters-apply]').click();
  await expect(toggle).toHaveAttribute('data-invalid', 'true');
  await expect(productRow(page, cheap.sku)).toBeVisible();
  await expect(productRow(page, dear.sku)).toBeVisible();
  await toggle.click();
  await expect(priceFrom).toHaveClass(/ion-invalid/);
  await expect(priceFrom.locator('.error-text')).toHaveText(/This is not an amount|Esto no es un importe/);
  await page.screenshot({ path: shot('FIX-DATATABLE-HUB-FILTERS-2A-inventory-error-1440') });
});

// Last of the file: the hundred tax categories it makes stay until `afterAll` cleans them.
test('selectores de Inventario (Combo compartido): a product whose category and tax category lie beyond the first page opens with their names', async ({
  page,
  context,
}) => {
  // flow: selectores de Inventario (Combo compartido) — more than one query (100) of each: the form asks for them
  await login(page, A, '/inventory/products');
  const tag = stamp();
  const lower = tag.toLowerCase();
  const rows = Array.from({ length: 100 }, (_, i) => ({ line: i + 2, name: `E2E Bulk ${tag} ${String(i).padStart(3, '0')}` }));
  const bulk = await api<{ created: number }>(context, A, 'POST', '/inventory/categories/bulk_create', { rows });
  expect([bulk.status, bulk.data.created]).toEqual([200, 100]);
  const far = await api<{ id: string }>(context, A, 'POST', '/inventory/categories', { name: `E2E Zz far ${tag}` });
  expect(far.status).toBe(201);
  for (let start = 0; start < 100; start += 10) {
    const made = await Promise.all(
      Array.from({ length: 10 }, (_, i) =>
        api(context, A, 'POST', '/tax/categories', { key: `e2e.inv_bulk_${lower}_${start + i}`, name: `E2E bulk tax ${start + i}` }),
      ),
    );
    expect(made.map((res) => res.status)).toEqual(Array(10).fill(201));
  }
  const farKey = `e2e.inv_zz_${lower}`;
  expect((await api(context, A, 'POST', '/tax/categories', { key: farKey, name: `ZZ E2E far tax ${tag}` })).status).toBe(201);
  const sku = `E2E-FAR-${tag}`;
  const product = await createProduct(context, { name: 'E2E Far', sku, tax_category_key: farKey, category_ids: [far.data.id] });

  await page.goto(`${A}/inventory/products`);
  await productsReady(page);
  await searchProducts(page, sku);
  await rowAction(page, 'inventory-products', product.id, 'edit');
  const form = dialog(page, 'inventory-product-form');
  await expect(form.locator('[data-testid=inventory-product-tax] input')).toHaveValue(`ZZ E2E far tax ${tag}`);
  await expect(form.locator('[data-testid^="inventory-product-categories-chip-"]')).toHaveText([`E2E Zz far ${tag}`]);
  await expect(form.locator('[data-testid=inventory-product-tax-unconfigured]')).toHaveCount(0);
  await form.locator('[data-testid^="inventory-product-categories-chip-"]').last().scrollIntoViewIfNeeded();
  await page.screenshot({ path: shot('FIX-INVENTORY-SEARCHSELECT-TO-COMBO-far-1280') });
  await form.locator('[data-testid=inventory-product-form-cancel]').click();
  await expect(form).toBeHidden();
});

// Importing and categories in Chrome against the real Taxes app (apps/inventory/WORKBOOK.md):
//   - INVENTORY-F09: a semicolon CSV (Excel in Spanish) opens «Check the import» with its columns
//     guessed, the rehearsal of the whole file (ready rows, problems, rows already in the catalog),
//     then «CSV tax categories» for the text Taxes does not know; the report counts created, skipped
//     and failed rows with their line;
//   - INVENTORY-F06/F07/F10: a category is created, edited and deleted (what will happen is said
//     first); a CSV of categories is imported with its report.
import { writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
import { cleanInventory, createProduct, dialog, fill, pick, productBySku, productsReady, shootFlow, stamp } from './inventory-helpers';

test.afterAll(() => {
  cleanInventory();
});

function csvFile(name: string, lines: string[]): string {
  const path = join(tmpdir(), `${name}-${Date.now()}.csv`);
  writeFileSync(path, `${lines.join('\r\n')}\r\n`, 'utf8');
  return path;
}

test('INVENTORY-F09: a CSV is checked first, its unknown tax text is asked for, and the report counts every row', async ({ page, context }) => {
  const run = stamp();
  await login(page, A, '/inventory/products');
  await productsReady(page);
  const existing = await createProduct(context, { name: 'E2E Existing', sku: `E2E-IMP-OLD-${run}` });
  const text = `e2e vino ${run.toLowerCase()}`;
  const file = csvFile('inventory-import', [
    'Nombre;Código;Precio;Stock;IVA',
    // Taxes reads its own key (as the export writes it), its name or a learned text.
    `E2E Imported coffee;E2E-IMP-1-${run};2,20;3;product.generic`,
    `E2E Imported wine;E2E-IMP-2-${run};9,50;6;${text}`,
    `E2E Bad price;E2E-IMP-3-${run};abc;1;product.generic`,
    `E2E Again;${existing.sku};1;1;product.generic`,
  ]);

  await shown(page).locator('[data-testid=inventory-products-csv-import]').setInputFiles(file);

  const preview = dialog(page, 'inventory-import-preview');
  await expect(preview).toBeVisible();
  const columns = preview.locator('[data-testid=inventory-import-column]');
  await expect(columns).toHaveCount(5);
  // The rehearsal of the whole file: 2 ready, 1 with a problem (its line and reason), 1 already there.
  const summary = preview.locator('[data-testid=inventory-import-summary]');
  await expect(summary).toContainText(/2 (row\(s\) ready|fila\(s\) listas) · 1/);
  await expect(preview.locator('[data-testid=inventory-import-reason]')).toHaveCount(1);
  await expect(preview.locator('[data-testid=inventory-import-reason]')).toContainText(/(Line|Línea) 4/);
  await expect(preview.locator('[data-testid=inventory-import-skipped]')).toBeVisible();
  await page.screenshot({ path: shot('inventory-import-preview-1280') });
  await shootFlow(page, 'INVENTORY-F09');
  await preview.locator('[data-testid=inventory-import-preview-submit]').click();

  // Taxes reads its key by itself; the new text is asked for and learned.
  const taxes = dialog(page, 'inventory-import-tax');
  await expect(taxes).toBeVisible();
  await expect(taxes.locator('[data-testid=inventory-import-tax-text]')).toHaveText([`«${text}»`]);
  await pick(page, taxes.locator('[data-testid=inventory-import-tax-category-0]'), /(Product — generic|Producto — general)/);
  await page.screenshot({ path: shot('inventory-import-tax-1280') });
  await taxes.locator('[data-testid=inventory-import-tax-submit]').click();

  const report = dialog(page, 'inventory-import-report');
  await expect(report).toBeVisible();
  const count = (id: string) => report.locator(`[data-testid=inventory-import-report-count-${id}] ion-note`);
  await expect(count('rows')).toHaveText('4');
  await expect(count('created')).toHaveText('2');
  await expect(count('skipped')).toHaveText('1');
  await expect(count('failed')).toHaveText('1');
  await expect(report.locator('[data-testid=inventory-import-report-failed-line]')).toContainText(`E2E-IMP-3-${run}`);
  await page.screenshot({ path: shot('inventory-import-report-1280') });
  await report.locator('[data-testid=inventory-import-report-close-button]').click();

  const wine = await productBySku(context, `E2E-IMP-2-${run}`);
  expect([wine.tax_category_key, wine.stock]).toEqual(['product.generic', '6.000']);
  expect((await productBySku(context, existing.sku)).name).toBe('E2E Existing');
});

test('INVENTORY-F06/F07/F10: a category is created, edited and deleted; a CSV of categories is imported', async ({ page }) => {
  const name = `E2E Drinks ${stamp()}`;
  await login(page, A, '/inventory/categories');
  await shown(page).locator('[data-testid=inventory-categories-row], [data-testid=inventory-categories-empty]').first().waitFor();

  await shown(page).locator('[data-testid=inventory-categories-add]').click();
  const form = dialog(page, 'inventory-category-form');
  await fill(form, 'inventory-category-name', name);
  await pick(page, form.locator('[data-testid=inventory-category-tax]'), /(Restaurant — drink|Restauración — bebida|Restaurante — bebida).*10/);
  await page.screenshot({ path: shot('inventory-category-new-1280') });
  await shootFlow(page, 'INVENTORY-F06');
  await form.locator('[data-testid=inventory-category-form-submit]').click();
  await expect(form).toBeHidden();
  await shown(page).locator('[data-testid=inventory-categories-search] input').fill(name);
  const row = shown(page).locator('[data-testid=inventory-categories-row]', { hasText: name });
  await expect(row).toBeVisible();

  await row.click();
  await expect(form).toBeVisible();
  await fill(form, 'inventory-category-name', `${name} bar`);
  await form.locator('[data-testid=inventory-category-form-submit]').click();
  await expect(form).toBeHidden();
  const renamed = shown(page).locator('[data-testid=inventory-categories-row]', { hasText: `${name} bar` });
  await expect(renamed).toBeVisible();

  const id = await renamed.getAttribute('data-id');
  const deleteButton = shown(page).locator(`[data-testid=inventory-categories-row-${id}-delete]`);
  if (await deleteButton.isVisible()) await deleteButton.click();
  else {
    await shown(page).locator(`[data-testid=inventory-categories-row-${id}-menu]`).click();
    await page.locator(`ion-popover [data-testid=inventory-categories-row-${id}-delete]`).click();
  }
  const confirm = page.locator('ion-modal.ep-form-modal').filter({ hasText: /Delete and unlink|Eliminar y desvincular/ });
  await expect(confirm).toContainText(/0 (product\(s\) will lose|producto\(s\) quedarán)/);
  await page.screenshot({ path: shot('inventory-category-delete-1280') });
  await shootFlow(page, 'INVENTORY-F07');
  await confirm.locator('.ep-form-modal__submit').click();
  await expect(confirm).toBeHidden();
  await expect(renamed).toHaveCount(0);

  const file = csvFile('inventory-categories', ['name;slug', `${name} one;`, `${name} two;e2e-two-${stamp().toLowerCase()}`, ';']);
  await shown(page).locator('[data-testid=inventory-categories-csv-import]').setInputFiles(file);
  const report = dialog(page, 'inventory-import-report');
  await expect(report).toBeVisible();
  await expect(report.locator('[data-testid=inventory-import-report-count-created] ion-note')).toHaveText('2');
  await expect(report.locator('[data-testid=inventory-import-report-count-failed] ion-note')).toHaveText('0');
  await shootFlow(page, 'INVENTORY-F10');
  await report.locator('[data-testid=inventory-import-report-close-button]').click();
  await shown(page).locator('[data-testid=inventory-categories-search] input').fill(`${name} t`);
  await expect(shown(page).locator('[data-testid=inventory-categories-row]', { hasText: `${name} two` })).toBeVisible();
});

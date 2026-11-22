// The preview of Files on a CSV separated by semicolons, as Excel saves it in Spanish and the Hub exports it in
// Spanish: each value in its own column and an amount with a decimal comma in one cell.
import { expect, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, signedInSpanish, testid } from './helpers';

const VIEWPORTS = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1440, height: 900 },
] as const;

const CSV = 'proveedor;concepto;importe\nQA Proveedor;Harina 25 kg;18,50\nQA Proveedor;Aceite 5 l;27,90\n';

for (const viewport of VIEWPORTS) {
  test(`BASE-F74 — a CSV separated by semicolons shows its own columns at ${viewport.width}`, async ({ browser }) => {
    const name = `compras-${viewport.width}.csv`;
    const { context, page } = await signedInSpanish(browser, viewport, '/files');
    try {
      await testid(page, 'files-upload-input').setInputFiles({ name, mimeType: 'text/csv', buffer: Buffer.from(CSV) });
      await page.locator(`[data-item="${name}"] [data-testid="files-item-main"]`).click();

      const preview = page.locator('[data-testid="file-preview"]').last();
      const table = preview.locator('[data-testid="file-preview-table"]');
      await expect(table.locator('th')).toHaveText(['proveedor', 'concepto', 'importe']);
      await expect(table.locator('tbody tr').first().locator('td')).toHaveText(['QA Proveedor', 'Harina 25 kg', '18,50']);
      await expect(table.locator('tbody tr').last().locator('td')).toHaveText(['QA Proveedor', 'Aceite 5 l', '27,90']);
      expect(await horizontalOverflow(page), 'no sideways scroll').toBeLessThanOrEqual(0);
      await capture(page, `APP-BASE-8-BASE-F74-csv-semicolons-${viewport.width}x${viewport.height}`);
    } finally {
      await api(context, A, 'POST', '/files/delete', { path: name });
      await context.close();
    }
  });
}

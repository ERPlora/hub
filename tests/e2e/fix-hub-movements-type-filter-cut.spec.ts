// flow: INVENTORY-F16 (hub#2045) — with the Hub in Spanish, the type filter of Inventory → Movements reads
// «Todos los tipos» whole on a phone, a tablet and a computer: Ionic's select fills its box, and the table's
// toolbar used to cap a filter the page adds at 8rem, which cut it to «Todos los tip…».
import { expect, test } from '@playwright/test';

import { capture, saveSessionForTheSweep, signedInSpanish, testid } from './helpers';

const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1440', width: 1440, height: 900 },
];

for (const size of SIZES) {
  test(`INVENTORY-F16: in Spanish the type filter of Movements reads whole at ${size.label}`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, size, '/inventory/movements');
    try {
      const shown = testid(page, 'inventory-movements-type-filter').locator('.select-text');
      await expect(shown).toHaveText('Todos los tipos');
      const cut = await shown.evaluate((text) => text.scrollWidth > text.clientWidth);
      expect(cut, 'the filter cuts «Todos los tipos»').toBe(false);
      await capture(page, `FIX-HUB-MOVEMENTS-TYPE-FILTER-${size.label}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });
}

// flow: SALE-F01, SALE-F11, SALE-F20 — hub#2751: on a tablet that loses its network the till said nothing, and a tap
// on a product said its options could not be read. In Spanish, with a dish on the check, the browser goes offline: the
// till keeps the check and says «Reconectando…» above its grid, at 375×667, 820×1180 and 1440×900 with nothing past the
// right edge; a tap on the dish says the connection is missing and adds nothing. With the network back the band goes and
// the check is still there. What a run creates, the product `E2E-OFFLINE-<run>` and its check, is deleted after it.
import { expect, test } from '@playwright/test';

import { A, shown } from './helpers';
import type { Product } from './inventory-helpers';
import { checkWithDish, cleanTill, dishForTheTill, linesOf, stamp } from './sale-helpers';
import { capturedAtEachSize } from './screen';
import { toastSaying } from './toast-helpers';

const KEY = 'FIX-HUB-2751-SALE-OFFLINE';
const RUN = stamp();
const NO_CONNECTION = 'No se pudo conectar con el servidor. Revisa tu conexión y vuelve a intentarlo en unos segundos.';
/** The live connection notices a lost network at once, or at the latest when 45 s pass without a frame. */
const NOTICED_MS = 60_000;

let dish: Product;

test.beforeAll(async ({ browser }) => {
  dish = await dishForTheTill(browser, 'OFFLINE', RUN);
});

test.afterAll(cleanTill);

test('SALE-F01: offline, the till says «Reconectando…» and a tap on a product says the connection is missing', async ({ browser }) => {
  test.setTimeout(180_000);
  const context = await browser.newContext({ baseURL: A, locale: 'es-ES', viewport: { width: 1440, height: 900 } });
  try {
    const page = await context.newPage();
    await checkWithDish(page, context, 'es', dish);
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    const band = shown(page).locator('[data-testid=pos-reconnecting]');
    const total = shown(page).locator('[data-testid=pos-total]');
    await expect(total).toContainText('7,00');
    await expect(band).toHaveCount(0);

    await context.setOffline(true);
    await expect(band).toHaveText('Reconectando…', { timeout: NOTICED_MS });
    await expect(linesOf(page, dish), 'the check stays as it was').toHaveCount(1);
    await expect(total, 'and so does its total').toContainText('7,00');
    await capturedAtEachSize(page, KEY, 'pos-reconnecting');

    await shown(page).locator(`[data-testid=pos-product-${dish.id}]`).click();
    await expect(toastSaying(page, NO_CONNECTION)).toBeVisible();
    await expect(toastSaying(page, 'suplementos'), 'never the options').toHaveCount(0);
    await expect(linesOf(page, dish), 'nothing is added').toHaveCount(1);

    await context.setOffline(false);
    await expect(band, 'the band goes once the connection is back').toHaveCount(0, { timeout: NOTICED_MS });
    await expect(linesOf(page, dish)).toHaveCount(1);
  } finally {
    await context.close();
  }
});

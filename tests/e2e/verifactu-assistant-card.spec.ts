// hub#2183: asked from the assistant, VeriFactu's connection test showed «Ejecutar en VeriFactu:» with nothing after
// the colon, and the test invoice «Crear en VeriFactu. Revisa cada dato antes de seguir.» with no datum under it. Now
// each card names its action as the button of Settings › Live test does, and the test invoice's says its series, its
// price and its VAT before the word is typed. End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder,
// «El asistente»). Both are cancelled: nothing is tested, issued nor sent to the AEAT.
// flow: VERIFACTU-F10 VERIFACTU-F11 BASE-F97
import { expect, type Page, test } from '@playwright/test';

import { cardSpec, fieldsOf, VIEWPORTS } from './assistant-card-helpers';
import { cancel, card, openPanelAtTheDesk, ownerIn } from './assistant-panel';
import { capture, psql } from './helpers';

cardSpec(['verifactu'], () => undefined);

const SAID = {
  es: {
    connection: 'Probar la conexión en VeriFactu.',
    invoice: 'Crear factura de prueba en VeriFactu. Revisa cada dato antes de seguir.',
    lines: ['Serie: TICKET', 'Precio: 1,00 €', 'IVA: 21 %'],
  },
  en: {
    connection: 'Test the connection in VeriFactu.',
    invoice: 'Create test invoice in VeriFactu. Check each datum before going on.',
    lines: ['Series: TICKET', 'Price: €1.00', 'VAT: 21%'],
  },
} as const;

/** The connection tests and the test invoices of `a` so far: a cancelled card adds neither. */
const ran = (): string =>
  psql(
    "select (select count(*) from verifactu_event where kind = 'connection_test') || '|' || " +
      "(select count(*) from invoice_invoiceline where description = 'Prueba VeriFactu')",
  );

const message = (page: Page) => card(page).locator('.assistant-confirm-text').first();

for (const language of ['es', 'en'] as const) {
  test(`verifactu-assistant-card — in ${language}, the connection test and the test invoice say what they will do`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    await openPanelAtTheDesk(page);
    const before = ran();

    expect(await fieldsOf(page, 'verifactu__diagnostic__run', {})).toEqual([]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(message(page)).toHaveText(SAID[language].connection);
      await capture(page, `hub-2183-verifactu-connection-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    const fields = await fieldsOf(page, 'verifactu__test_invoice__create', {});
    expect(fields.map((field) => field.name)).toEqual(['series', 'price', 'vat']);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(message(page)).toHaveText(SAID[language].invoice);
      for (const line of SAID[language].lines) await expect(card(page)).toContainText(line);
      await capture(page, `hub-2183-verifactu-test-invoice-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    expect(ran()).toBe(before);
    await context.close();
  });
}

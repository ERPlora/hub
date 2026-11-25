// flow: assistant-card (BASE-F97 SERVICE-F03 SALE-F35 INVENTORY-F01)
// The one line of a normal write's card: what it touches by its value, every datum after it by the name its screen
// gives it. A minimum price and a price, a duration or a position used to go bare («Mechas · 65,00 €» for both prices),
// and who confirmed could not tell what would change. A tax category says the rate it charges today, as the Sections
// screen does. Cancelled: nothing is changed or created.
import { expect, test } from '@playwright/test';

import { VIEWPORTS } from './assistant-card-helpers';
import { askForACard, cancel, cancelAtComputerSize, captureStill, card, leave, openPanelAtTheDesk, openPanelInSpanish, signedInWith } from './assistant-panel';
import { panelSpec } from './provider-helpers';
import { post } from './service-helpers';

panelSpec();

test('BASE-F97 SERVICE-F03 — in Spanish the card says which price of a service changes and that its duration is minutes', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-LINE-NAMES-SERVICE';
  const { context, page, turnedOn } = await signedInWith(browser, ['service']);
  const name = `E2E Mechas ${Date.now().toString(36)}`;
  const service = await post<{ id: string }>(context, '/service/services', {
    name,
    price: 6000,
    duration_minutes: 60,
    tax_category_key: 'service.generic',
  });
  await openPanelInSpanish(page);
  await askForACard(page, `E2E-ASK service__service__update ${JSON.stringify({ id: service.id, min_price: 6500 })}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(new RegExp(`Cambiar en Servicios: ${name} · Precio mínimo: 65,00\\s€`));
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await askForACard(page, `E2E-ASK service__service__update ${JSON.stringify({ id: service.id, price: 6500 })}`);
  await expect(card(page)).toContainText(new RegExp(`Cambiar en Servicios: ${name} · Precio: 65,00\\s€`));
  await cancelAtComputerSize(page);
  await askForACard(page, `E2E-ASK service__service__update ${JSON.stringify({ id: service.id, duration_minutes: 45 })}`);
  await expect(card(page)).toContainText(`Cambiar en Servicios: ${name} · Duración (minutos): 45`);
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

const RATED = {
  es: {
    open: openPanelInSpanish,
    section: /Crear en .+: E2E Varios · Categoría fiscal: Producto — general · 21\s% · Posición: 0/,
    product: /Crear en .+: E2E Cuchara · Precio: 2,50\s€ · Categoría fiscal: Restauración — comida · 10\s%/,
  },
  en: {
    open: openPanelAtTheDesk,
    section: /Create in .+: E2E Varios · Tax category: Product — generic · 21% · Position: 0/,
    product: /Create in .+: E2E Cuchara · Price: €2\.50 · Tax category: Restaurant — food · 10%/,
  },
};
for (const language of ['es', 'en'] as const) {
  test(`BASE-F97 SALE-F35 INVENTORY-F01 — in ${language} the card of a new section and of a new product says the VAT each charges today`, async ({ browser }) => {
    const KEY = `FIX-HUB-2263-CARD-TAX-RATE-${language}`;
    const { context, page, turnedOn } = await signedInWith(browser, ['tax', 'sale', 'inventory']);
    await RATED[language].open(page);
    const section = { name: 'E2E Varios', tax_category_key: 'product.generic', sort_order: 0 };
    const product = { name: 'E2E Cuchara', sku: 'E2E-CUCHARA', price: 250, tax_category_key: 'restaurant.food' };
    for (const [what, tool, data] of [['section', 'sale__department__create', section], ['product', 'inventory__product__create', product]] as const) {
      await askForACard(page, `E2E-ASK ${tool} ${JSON.stringify(data)}`);
      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await expect(card(page)).toContainText(RATED[language][what]);
        await captureStill(page, `${KEY}-${what}-${vp.label}`);
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      await cancel(page);
    }
    await leave(context, turnedOn);
  });
}

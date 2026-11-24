// flow: assistant-card (BASE-F97 SERVICE-F03 SALE-F35)
// The one line of a normal write's card: what it touches by its value, every datum after it by the name its screen
// gives it. A minimum price and a price, a duration or a position used to go bare («Mechas · 65,00 €» for both prices),
// and who confirmed could not tell what would change. Cancelled: nothing is changed or created.
import { expect, test } from '@playwright/test';

import { askForACard, cancelAtComputerSize, captureStill, card, leave, openPanelInSpanish, signedInWith } from './assistant-panel';
import { THREE_SIZES as VIEWPORTS } from './helpers';
import { post } from './service-helpers';

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

test('BASE-F97 SALE-F35 — in Spanish the card of a new section says its position by name', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-LINE-NAMES-POSITION';
  const { context, page, turnedOn } = await signedInWith(browser, ['tax', 'sale']);
  await openPanelInSpanish(page);
  const section = { name: 'E2E Varios', tax_category_key: 'product.generic', sort_order: 0 };
  await askForACard(page, `E2E-ASK sale__department__create ${JSON.stringify(section)}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(/Crear en .+: E2E Varios · Categoría fiscal: .+ · Posición: 0/);
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

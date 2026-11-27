// flow: SERVICE-F01 BASE-F97
// A new service asked for through the assistant without its price draws no card: the assistant has to ask how much it
// costs first, never create it at 0. Its card says the name, the price and the duration it is created with, the
// Settings' one when none was said. Cancelled: nothing is created.
import { expect, test } from '@playwright/test';

import { VIEWPORTS } from './assistant-card-helpers';
import { ask, askForACard, cancelAtComputerSize, captureStill, card, lastAnswer, leave, openPanelInSpanish, signedInWith } from './assistant-panel';
import { NOT_DONE } from './assistant-provider';
import { A, api } from './helpers';
import { panelSpec } from './provider-helpers';

panelSpec();

test('SERVICE-F01 BASE-F97 — in Spanish a new service without its price draws no card, and its card says its price and the duration it takes', async ({ browser }) => {
  const KEY = 'FIX-HUB-2677-NEW-SERVICE-PRICE';
  const { context, page, turnedOn } = await signedInWith(browser, ['service']);
  const name = `E2E Corte y peinado ${Date.now().toString(36)}`;
  const settings = await api<{ default_duration: number }>(context, A, 'GET', '/service/settings');
  await openPanelInSpanish(page);
  // Refused before any card, the model hears which datum is missing; a card waiting for a yes would hold this answer.
  await ask(page, `E2E-ASK service__service__create ${JSON.stringify({ name })}`, { settle: false });
  await expect(lastAnswer(page)).toContainText(NOT_DONE.es);
  await expect(card(page)).toBeHidden();
  await askForACard(page, `E2E-ASK service__service__create ${JSON.stringify({ name, price: 2500 })}`);
  const line = new RegExp(`Crear en Servicios: ${name} · Precio: 25,00\\s€ · Duración[^:]*: ${settings.data.default_duration}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(line);
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  const found = await api<{ total: number }>(context, A, 'GET', `/service/services?search=${encodeURIComponent(name)}`);
  expect(found.data.total).toBe(0);
  await leave(context, turnedOn);
});

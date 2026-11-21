// What the card of the Hub's assistant says of each datum, in Spanish, set up as in base-assistant.spec.ts: its
// label, an object by its values, no attempt key, a file by its name and an amount in its currency.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { ask, askForACard, askForAPriceInDollars, cancelAtComputerSize, captureConfirmation, captureStill, card, decide, lastAnswer, leave, openPanelAtTheDesk, openPanelInSpanish, panel, sentCard, signedInWith } from './assistant-panel';
import { A, api, login, THREE_SIZES as VIEWPORTS } from './helpers';
import { cleanPricing, CODE as PRICING_CODE, createProduct, post, TAG as PRICING_TAG } from './pricing-helpers';
import { panelSpec } from './provider-helpers';

panelSpec();

/** The last receipt under the answers: what the Hub says it did with a write (BASE-F97, step 5). */
const receipt = (page: Page): Locator => panel(page).locator('[data-testid="assistant-receipt"]').last();

// Cancelled: nothing changes, so the only thing to clean is the language cookie's context, closed at the end.
test('BASE-F97 BASE-F98 — in Spanish the card names every datum in Spanish, also one the screen does not name itself, and the platform by its screen', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  // In Spanish (the Hub's language cookie, as the sign-in sets it).
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const before = await api<Record<string, unknown>>(context, A, 'GET', '/access/settings');
  expect(before.status, JSON.stringify(before.data)).toBe(200);
  await openPanelAtTheDesk(page);
  await askForACard(page, 'E2E-ASK base__access__settings_update {"pin_inactivity_minutes":10,"pin_length":6}');
  await expect(card(page)).toContainText('¿Ejecutar esta acción?');
  await expect(card(page)).not.toContainText('Pin Length');
  await expect(card(page)).not.toContainText('Pin Inactivity Minutes');
  await expect(card(page)).not.toContainText('Base');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Cambiar en Ajustes. Revisa cada dato antes de seguir.');
    await expect(card(page)).toContainText('Volver a pedir tras (minutos): 10');
    await expect(card(page)).toContainText('Dígitos del PIN: 6');
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toHaveText('No se hizo, cancelado: Cambiar en Ajustes');
  expect((await api(context, A, 'GET', '/access/settings')).data).toEqual(before.data);
  await context.close();
});

// flow: assistant-card (BASE-F97 BASE-F98)
// An object datum is said by its values, as a summary says an address. Cancelled: nothing is sent.
test('assistant-card — in Spanish an object datum (a WhatsApp template) is said by its values, never by its inner keys', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-OBJECT-SHOWS-INNER-KEYS-IN-ENGLISH';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await openPanelInSpanish(page);
  const send = {
    to: '+34600111222',
    template: { name: 'cita_recordatorio', language: 'es', variables: ['Ana', '10:00'] },
    client_message_id: '0192f5a0-0000-7000-8000-000000000001',
  };
  await askForACard(page, `E2E-ASK whatsapp_inbox__message__send ${JSON.stringify(send)}`);
  await expect(card(page)).toContainText('Enviar en Bandeja de WhatsApp. Revisa cada dato antes de seguir.');
  for (const inner of ['name:', 'language:', 'variables:']) await expect(card(page)).not.toContainText(inner);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Plantilla: cita_recordatorio · es · Ana, 10:00');
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await context.close();
});

// flow: base-assistant-card-attempt-keys (BASE-F97)
// A write's attempt key is nothing a person can judge, so the card leaves it out; the write still gets it whole, and
// the same print asked again with its key, as a retry, is still one job.
test('base-assistant-card-attempt-keys — in Spanish a print leaves its key out of the card and runs with it: asked twice, it is one job', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-ATTEMPT-KEYS';
  const { context, page, turnedOn } = await signedInWith(browser, ['printing']);
  await openPanelInSpanish(page);
  const stamp = Date.now();
  const product = `Café ${stamp}`;
  const jobKey = `e2e-attempt-${stamp}`;
  const print = { job_key: jobKey, document_type: 'barcode_label', document: { product_name: product, barcode: '8412345678905', price: 1.5 } };
  const jobs = async () =>
    (await api<{ rows: { reference: string }[] }>(context, A, 'GET', `/printing/jobs?search=${encodeURIComponent(product)}`)).data.rows;
  await askForACard(page, `E2E-ASK printing__job__create ${JSON.stringify(print)}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    // The document by the queue's word for it, never as the model sent it.
    await expect(card(page)).toContainText(`Crear en Impresión: Etiqueta de código de barras · ${product}`);
    await expect(card(page)).not.toContainText(jobKey);
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  // The Hub's receipt says it ran, and so does the answer: a job that can be cancelled is no refusal.
  await decide(page, 'submit');
  await expect(receipt(page)).toHaveText('Hecho: Crear en Impresión');
  await expect(lastAnswer(page)).toHaveText('Hecho.');
  expect(await jobs()).toHaveLength(1);
  // The same print again, with its key: a retry. Its card leaves the key out again, and it adds no second job.
  await askForACard(page, `E2E-ASK printing__job__create ${JSON.stringify(print)}`);
  await expect(card(page)).not.toContainText(jobKey);
  await decide(page, 'submit');
  await expect(receipt(page)).toHaveText('Hecho: Crear en Impresión');
  await expect(panel(page).locator('[data-testid="assistant-receipt"]')).toHaveCount(2);
  await expect(lastAnswer(page)).toHaveText('Hecho.');
  expect(await jobs()).toHaveLength(1);
  await leave(context, turnedOn);
});

// flow: whatsapp_inbox-assistant-card (WHATSAPP_INBOX-F33)
// A template with a document header: the file goes by the name it was chosen with, never by its id, and the message
// key never shows. Cancelled: nothing is sent.
test('whatsapp_inbox-assistant-card — in Spanish a template names its header file by its name and leaves the message key out', async ({ browser }) => {
  const KEY = 'FIX-HUB-WHATSAPP-INBOX-ATTEMPT-KEYS-UNMARKED';
  const { context, page, turnedOn } = await signedInWith(browser, ['customer', 'whatsapp_inbox']);
  const stamp = Date.now();
  const file = `carta-${stamp}.pdf`;
  const pdf = Buffer.from(`%PDF-1.7\n${'\u0000'.repeat(64)}`, 'latin1').toString('base64');
  const kept = await api<{ id: string; name: string }>(context, A, 'POST', '/whatsapp_inbox/templates/samples', {
    header_format: 'DOCUMENT',
    name: file,
    content_base64: pdf,
  });
  expect(kept.status, `keep the header's file: ${JSON.stringify(kept.data)}`).toBe(201);
  await openPanelInSpanish(page);
  // A UUID, as the screen generates it: anything else is refused before the card (`invalid_arguments`, hub#741).
  const messageKey = crypto.randomUUID();
  const send = {
    to: '+34600111222',
    template: { name: 'carta_del_dia', language: 'es', header_sample: kept.data.id },
    client_message_id: messageKey,
  };
  await askForACard(page, `E2E-ASK whatsapp_inbox__message__send ${JSON.stringify(send)}`);
  await expect(card(page)).toContainText('Enviar en Bandeja de WhatsApp. Revisa cada dato antes de seguir.');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Plantilla: carta_del_dia · es · ${file}`);
    await expect(card(page)).not.toContainText(messageKey);
    await expect(card(page)).not.toContainText(kept.data.id);
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

// flow: base-assistant-money-mark (BASE-F97)
// The card knows an amount by the money mark its app declares, whatever its description says («in minor units of the
// currency»), so 1500 reads «15,00 €». Cancelled: nothing is recorded.
test('base-assistant-money-mark — in Spanish a payment says its amount in the business’s currency, never in its minor unit', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS';
  const { context, page, turnedOn } = await signedInWith(browser, ['payment']);
  await openPanelInSpanish(page);
  const payment = { method: 'Caja', payment_date: '2026-11-02', amount: 1500, beneficiary_name: 'Cafés del Sur' };
  await askForACard(page, `E2E-ASK payment__payment__create ${JSON.stringify(payment)}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(/Caja · 2 nov 2026 · 15,00\s€/);
    await expect(card(page)).not.toContainText('1500');
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

// flow: base-assistant-money-mark (BASE-F97)
// The same PR: a payment in dollars of a business in euros said «15,00 €», every amount in the business's currency. Now in
// the currency its write names, with that currency's decimals (none in yen), as Stripe or Square show it. Cancelled.
test('base-assistant-money-mark — in Spanish a payment in another currency says its amount in it, with its decimals', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS-USD';
  const { context, page, turnedOn } = await signedInWith(browser, ['payment']);
  await openPanelInSpanish(page);
  const payment = { method: 'Caja', payment_date: '2026-11-02', amount: 1500, beneficiary_name: 'Cafés del Sur', currency: 'USD' };
  await askForACard(page, `E2E-ASK payment__payment__create ${JSON.stringify(payment)}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(/Caja · 2 nov 2026 · 15,00\s\$/);
    await expect(card(page)).not.toContainText('€');
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  // In yen, without decimals: 1500 is ¥1,500, never «15,00».
  await ask(page, `E2E-ASK payment__payment__create ${JSON.stringify({ ...payment, currency: 'JPY' })}`, { settle: false });
  await expect(card(page)).toContainText(/Caja · 2 nov 2026 · 1\.500\s¥/); // Its thousands grouped, as every amount of the Hub (hub#734).
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  await leave(context, turnedOn);
});

// flow: base-assistant-money-mark (BASE-F97)
// The same PR: a price set on a price list in dollars said «15,00 €»: the write names the list, not its currency. The
// card reads the list as the person and says the price in its currency (a list is always in one with two decimals), as
// Shopify shows a price of a market. Cancelled: no price is set. What it creates carries the pricing specs' code and
// goes away.
test('base-assistant-money-mark — in Spanish a price set on a list in another currency says it in that currency', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS-LIST-USD';
  const NEEDED = ['inventory', 'customer', 'pricing'];
  const { context, page, turnedOn } = await signedInWith(browser, NEEDED);
  cleanPricing();
  const product = `${PRICING_TAG} Champú ${Date.now().toString(36)}`;
  await createProduct(context, product, `${PRICING_CODE}-USD`, 1250);
  for (const [code, currency] of [[`${PRICING_CODE}USD`, 'USD'], [`${PRICING_CODE}PLN`, 'PLN']]) {
    await post(context, '/pricing/price_lists', { code, name: `${PRICING_TAG} ${currency}`, currency });
  }
  await openPanelInSpanish(page);
  const price = { product, price_list: `${PRICING_CODE}USD`, price: 1500 };
  await askForAPriceInDollars(page, 'pricing__price_item__add', price);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(new RegExp(`${PRICING_CODE}USD · 15,00\\s\\$`));
    await expect(card(page)).not.toContainText('€');
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  // In zlotys, the list's, never the business's euros.
  await ask(page, `E2E-ASK pricing__price_item__add ${JSON.stringify({ ...price, price_list: `${PRICING_CODE}PLN` })}`, { settle: false });
  await expect(card(page)).toContainText(new RegExp(`${PRICING_CODE}PLN · 15,00\\szł`));
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  cleanPricing();
  await leave(context, turnedOn);
});

// flow: base-assistant-money-mark (BASE-F97)
// The same PR: an amount inside a datum went worded by the server («13,50 US$», «1,50 PLN») and the one on top by the
// screen («1,50 $», «1,50 zł»): one currency, two ways on one card. Now the server sends every amount as money and the
// screen writes them all: charging a sale, its discount on top and the amount of its payment inside the list of payments
// arrive as the same money, in the same currency. Cancelled: nothing is charged.
test('base-assistant-money-mark — in Spanish an amount inside a datum and one on top arrive as the same money', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS-NESTED';
  const NEEDED = ['customer', 'tax', 'sale'];
  const { context, page, turnedOn } = await signedInWith(browser, NEEDED);
  await openPanelInSpanish(page);
  // A charge the write takes (hub#729: `invalid_arguments` refuses any other before the card): its key and a loose line,
  // because only a counter sale carries a discount of its own (a check's lives in the check).
  const sale = {
    idempotency_key: `e2e-charge-${Date.now().toString(36)}`,
    open_lines: [{ unit_price: 1500, tax_category_key: 'service.generic', name: 'E2E Corte' }],
    discount_amount: 150,
    payments: [{ method: 'Efectivo', amount: 1350 }],
  };
  const sent = sentCard(page);
  await askForACard(page, `E2E-ASK sale__sale__complete ${JSON.stringify(sale)}`);
  const fields = (await sent).fields;
  expect(fields.map((field) => field.name)).not.toContain('idempotency_key');
  const top = fields.find((field) => field.name === 'discount_amount');
  const payments = fields.find((field) => field.name === 'payments');
  expect(top).toMatchObject({ kind: 'money', value: 150 });
  expect(payments?.value).toEqual([{ method: 'Efectivo', amount: { kind: 'money', value: 1350 } }]);
  // The same currency, the card's: neither carries one of its own, so the screen writes both with one symbol.
  expect(top?.money ?? null).toBeNull();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(/1,50\s€/);
    await expect(card(page)).not.toContainText(/EUR|US\$|1350/);
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

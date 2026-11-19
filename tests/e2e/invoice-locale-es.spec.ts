// flow: invoice-locale — Django joins every app's Spanish catalogue and the first that translates a message wins, so
// the assistant's card could name the issuer's data with customer's words, «NIF/CIF» and «Dirección». Changing the
// issuer is a dangerous write, whose card lists every datum by its name: it names them as the Issuer screen does, «NIF»
// and «Domicilio». The owner, in Spanish, asks the assistant (the e2e's provider, `E2E-ASK`: assistant-provider.ts;
// README «El asistente») to change the issuer's tax ID and address; the card says them so at 390, 834 and 1440, and
// «Cancel» changes nothing. (A series' «Activa» rides a normal card, a single line of values with no names:
// apps/invoice/tests/test_i18n.py checks the name the server gives it.)

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { askForACard, cancelAtComputerSize, card, openPanel, type SentCard, sentCard } from './assistant-panel';
import { type Provider } from './assistant-provider';
import { emptyMonth } from './assistant-real';
import { A, capture, login, THREE_SIZES as VIEWPORTS } from './helpers';
import { issuerNow } from './invoice-helpers';
import { seededProvider } from './provider-helpers';

const KEY = 'FIX-HUB-INVOICE-ES-TEXTS-SHADOWED-BY-AN-EARLIER-APP';

let provider: Provider;

test.beforeAll(async () => {
  provider = await seededProvider();
});

test.afterAll(async () => {
  await provider?.close();
  emptyMonth();
});

test.beforeEach(() => {
  emptyMonth();
});

const labelsOf = (sent: SentCard) => Object.fromEntries(sent.fields.map((field) => [field.name, field.label]));

/** The owner on `a` in Spanish, on the Issuer screen: the Hub's language cookie, as the sign-in sets it. */
async function spanishOwner(context: BrowserContext): Promise<Page> {
  const page = await context.newPage();
  await login(page, A, '/invoice/issuer');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/invoice/issuer`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return page;
}

test('invoice-locale — in Spanish the dangerous card of changing the issuer says «NIF» and «Domicilio», as the Issuer screen does', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'es-ES' });
  try {
    const page = await spanishOwner(context);
    const issuerBefore = await issuerNow(context);
    await openPanel(page);

    // «Cambia el NIF y el domicilio del emisor»: both by the Issuer screen's words.
    const sent = sentCard(page);
    const issuer = { legal_name: 'e2e Peluquería Ana SL', tax_id: 'B76543214', address: 'Calle Sol 9' };
    await askForACard(page, `E2E-ASK invoice__issuer__update ${JSON.stringify(issuer)}`, { timeout: 30_000 });
    expect(labelsOf(await sent)).toMatchObject({ tax_id: 'NIF', address: 'Domicilio' });
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await expect(card(page)).toContainText('NIF: B76543214');
      await expect(card(page)).toContainText('Domicilio: Calle Sol 9');
      await expect(card(page)).not.toContainText('NIF/CIF');
      await expect(card(page)).not.toContainText('Dirección');
      await capture(page, `${KEY}-${viewport.label}`);
    }
    await cancelAtComputerSize(page);
    // Cancelled: the issuer is as it was.
    expect(await issuerNow(context)).toEqual(issuerBefore);
  } finally {
    await context.close();
  }
});

// hub#2671: asked to note that a customer says yes to the WhatsApp offers, the assistant asked for «the exact words she
// was shown» and recorded nothing. Now its card shows the business's own sentence to read out before «Run it», and
// running it leaves on her card the same consent, with the same sentence and version, as «They said yes» on the card.
// End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`; the
// SaaS seeded with it, README «El asistente»). What this file creates carries the customers' prefix (`e2e.`) and goes
// away; Customers, if this spec turned it on, is turned off again.
// flow: CUSTOMER-F14 BASE-F97
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { cardSpec, fieldsOf, VIEWPORTS } from './assistant-card-helpers';
import { card, decide, openPanelAtTheDesk, ownerIn, panel } from './assistant-panel';
import { cleanUp, e2eName, spanishMobile } from './customer-helpers';
import { A, api, capture, shown } from './helpers';
import { post } from './pricing-helpers';

const SENTENCE = 'Quiero recibir ofertas y novedades de este negocio por este canal. Puedo darme de baja cuando quiera.';

type Fact = { channel: string; state: string; notice_text: string; notice_version: string };

cardSpec(['customer'], cleanUp);

/** Every consent fact of the card, as its history reads it: channel, state, the words stored and their version. */
async function factsOf(context: BrowserContext, id: string): Promise<Fact[]> {
  const read = await api<{ rows: Fact[] }>(context, A, 'GET', `/customer/consents?customer_id=${id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  return read.data.rows.map(({ channel, state, notice_text, notice_version }) => ({ channel, state, notice_text, notice_version }));
}

async function atEachSize(page: Page, name: string, ready: () => Promise<void>): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await ready();
    await capture(page, `${name}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test('CUSTOMER-F14 — the assistant records a yes with the card’s own sentence, shown on its card to read out', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  const lucia = await post<{ id: string; name: string }>(context, '/customer/customers', { name: e2eName('Lucía Gómez'), phone: spanishMobile() });
  await openPanelAtTheDesk(page);

  // «Lucía dice que sí a las ofertas por WhatsApp»: nobody writes the words, the card brings them.
  const fields = await fieldsOf(page, 'customer__consent__grant', { customer: lucia.name, channel: 'whatsapp' });
  expect(fields.map((field) => [field.label, field.value])).toContainEqual(['Léelo en voz alta', SENTENCE]);
  await atEachSize(page, 'hub-2671-assistant-card', () => expect(card(page)).toContainText(`Léelo en voz alta: ${SENTENCE}`));
  await decide(page, 'submit');
  await expect.poll(() => factsOf(context, lucia.id)).toEqual([
    { channel: 'whatsapp', state: 'granted', notice_text: SENTENCE, notice_version: 'counter-v1' },
  ]);

  // Her card: WhatsApp given; «Registrar consentimiento» of another channel reads out the very same sentence, and its
  // yes is stored exactly as the assistant's.
  await panel(page).locator('[data-testid="assistant-close"]').click();
  await expect(panel(page)).toBeHidden();
  await page.goto(`/customer/customers/${lucia.id}`);
  const whatsapp = shown(page).locator('[data-testid=customer-consent-whatsapp]');
  await expect(whatsapp.locator('.customer-consent__state')).toHaveText('Dado');
  await shown(page).locator('[data-testid=customer-consent-sms-grant]').click();
  const ask = shown(page).locator('[data-testid=customer-consent-sms-ask]');
  await expect(ask.locator('.customer-consent__notice')).toHaveText(SENTENCE);
  await atEachSize(page, 'hub-2671-card-screen', async () => {
    await ask.scrollIntoViewIfNeeded();
    await expect(ask).toBeInViewport();
  });
  await shown(page).locator('[data-testid=customer-consent-sms-confirm]').click();
  await expect(shown(page).locator('[data-testid=customer-consent-sms] .customer-consent__state')).toHaveText('Dado');
  const [onScreen, byAssistant] = await factsOf(context, lucia.id);
  expect(onScreen.channel).toBe('sms');
  expect([onScreen.notice_text, onScreen.notice_version]).toEqual([byAssistant.notice_text, byAssistant.notice_version]);
  await context.close();
});

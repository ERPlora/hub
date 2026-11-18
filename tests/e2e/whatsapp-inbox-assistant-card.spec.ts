// hub#571: since hub#416 the assistant's card left out every id its schema does not mark, so «close Ana's conversation»,
// «delete that note», «retry that message» or «delete the reminder template» said no conversation, no message, no note
// and no template. Now each record of the WhatsApp inbox is named as its screens show it, read as the person, in their
// language, never by its id: the conversation as the inbox calls it, the card joined to it by Customers' own read, the
// message and the note by their text, the template by its name and its language. End to end with the stack's SaaS
// gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it
// (README of this folder, «El asistente»). Cancelled, nothing changes. What this file creates carries the inbox's and the
// customers' prefix and goes away; the apps it turns on are turned off again, and `a`'s photo and channel go back.
// flow: WHATSAPP_INBOX-F31 WHATSAPP_INBOX-F32 WHATSAPP_INBOX-F35 WHATSAPP_INBOX-F36 WHATSAPP_INBOX-F37 BASE-F97
import { expect, test } from '@playwright/test';

import { AN_ID, cancel, cardSpec, datumOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { cleanUp as cleanCustomers, e2eName } from './customer-helpers';
import { A, api, capture, psql, untilStill } from './helpers';
import { post } from './pricing-helpers';
import { cleanUp as cleanInbox, e2ePhone, keepPhoto, pushChannel, receive, restorePhoto, template } from './whatsapp-helpers';

/** A business is born with every app off; the inbox requires Customers, which names the card joined to it. */
const NEEDED = ['customer', 'whatsapp_inbox'];

/** What each screen calls the record, by the language of the card. */
const WORDS = {
  es: { conversation: 'Conversación', customer: 'Cliente', message: 'Mensaje', note: 'Nota', template: 'Plantilla' },
  en: { conversation: 'Conversation', customer: 'Customer', message: 'Message', note: 'Note', template: 'Template' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };
/** A template of `a`'s, as erplora.com's photo of Meta's list brings it. */
const TEMPLATE = 'e2e_cita';

test.beforeAll(keepPhoto);

cardSpec(NEEDED, () => {
  cleanInbox();
  cleanCustomers();
});

test.afterAll(restorePhoto);

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`whatsapp-inbox-assistant-card — in ${language}, a write of the inbox says which conversation, message, note or template, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    // Ana's first message, a note on her conversation, her customer card and a template of the business.
    const contact = e2eName('Ana López');
    const message = receive(e2ePhone(), 'Hola, ¿tenéis hora mañana?', contact);
    const note = await post<{ id: string; text: string }>(context, '/whatsapp_inbox/notes', {
      id: message.conversation_id,
      text: 'e2e. Prefiere las mañanas',
    });
    const ana = await post<{ id: string; name: string }>(context, '/customer/customers', { name: e2eName('Ana García') });
    pushChannel({ status: 'connected', templates: [template(TEMPLATE)] });
    const kept = psql(`select id from whatsapp_inbox_template where name = '${TEMPLATE}' and deleted_at is null`);
    expect(kept, 'the photo brought no template').not.toBe('');
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Cierra la conversación de Ana», a dangerous write: the conversation as the inbox calls it, in every size.
    const closed = await datumOf(page, 'whatsapp_inbox__conversation__set_status', { id: message.conversation_id, status: 'closed' });
    expect([closed.label, closed.value]).toEqual([words.conversation, contact]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.conversation}: ${contact}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-571-conversation-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Apunta en la conversación de Ana que llame mañana», a write that is not dangerous: said in one line.
    const noted = await datumOf(page, 'whatsapp_inbox__note__add', { id: message.conversation_id, text: 'e2e. Llamar mañana' });
    expect([noted.label, noted.value]).toEqual([words.conversation, contact]);
    await expect(card(page)).toContainText(contact);
    await cancel(page);

    // «Une la conversación a la ficha de Ana García»: the card joined, by Customers' own name for it.
    const linked = await datumOf(page, 'whatsapp_inbox__conversation__link_customer', { id: message.conversation_id, customer_id: ana.id }, 'customer_id');
    expect([linked.label, linked.value]).toEqual([words.customer, ana.name]);
    await expect(card(page)).toContainText(ana.name);
    await cancel(page);

    // «Reintenta ese mensaje» and «borra esa nota», dangerous: each by its text.
    const retried = await datumOf(page, 'whatsapp_inbox__message__retry', { id: message.id });
    expect([retried.label, retried.value]).toEqual([words.message, 'Hola, ¿tenéis hora mañana?']);
    await expect(card(page)).toContainText(`${words.message}: Hola, ¿tenéis hora mañana?`);
    await cancel(page);
    const removed = await datumOf(page, 'whatsapp_inbox__note__delete', { id: note.id });
    expect([removed.label, removed.value]).toEqual([words.note, note.text]);
    await expect(card(page)).toContainText(`${words.note}: ${note.text}`);
    await cancel(page);

    // «Borra la plantilla e2e_cita», dangerous: by its name and its language, as its sheet says it, in every size.
    const dropped = await datumOf(page, 'whatsapp_inbox__template__delete', { id: kept });
    expect([dropped.label, dropped.value]).toEqual([words.template, `${TEMPLATE} (es)`]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.template}: ${TEMPLATE} (es)`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await untilStill(page);
      await capture(page, `hub-571-template-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // Cancelled, nothing changed: the conversation open and without a card, the note there, the template not deleted.
    const conversation = await api<{ status: string; customer_id: string | null }>(
      context,
      A,
      'GET',
      `/whatsapp_inbox/conversations/detail?id=${message.conversation_id}`,
    );
    expect(conversation.status, JSON.stringify(conversation.data)).toBe(200);
    expect([conversation.data.status, conversation.data.customer_id]).toEqual(['open', null]);
    const notes = await api<{ rows: { id: string }[] }>(context, A, 'GET', `/whatsapp_inbox/notes?id=${message.conversation_id}`);
    expect(notes.data.rows.map((row) => row.id)).toEqual([note.id]);
    expect(psql(`select deleted_at is null from whatsapp_inbox_template where id = '${kept}'`)).toBe('t');
    await context.close();
  });
}

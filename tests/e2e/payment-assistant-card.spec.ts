// hub#674: since hub#416 the assistant's card left out every id its schema does not mark, so «cancel the payment
// PAY-…», «deactivate the BBVA account» or a new payment from a method said no payment and no method. Now a payment is
// named by its reference and a method by its name — as «Cancel payment — PAY-…» and «Editing method — …» say them —,
// read as the person, in their language, never by an id; the type of a method by the label of its form. End to end
// with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must
// be seeded with it (README of this folder, «El asistente»). Cancelled, nothing changes. What this file creates is
// named «E2E Tarjeta pago …» and goes away before and after; the app it turns on is turned off again.
// flow: PAYMENT-F02 PAYMENT-F05 PAYMENT-F08 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { cancel, cardSpec, datumOf, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, psql } from './helpers';
import { post } from './service-helpers';

const TAG = 'E2E Tarjeta pago';

/** What the lists call a payment and a method, and the label of the transfer type, by the language of the card. */
const WORDS = {
  es: { payment: 'Pago', method: 'Método', cash: 'Efectivo' },
  en: { payment: 'Payment', method: 'Method', cash: 'Cash' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

/** Every payment of a method of this file, its methods, and the counter of a day no payment is left of. */
function cleanUp(): void {
  const methods = `select id from payment_paymentmethod where name like '${TAG}%'`;
  psql(
    [
      `delete from payment_payment where method_id in (${methods}) or beneficiary_name like '${TAG}%'`,
      `delete from payment_paymentmethod where name like '${TAG}%'`,
      `delete from payment_paymentcounter c where not exists (select 1 from payment_payment p where p.reference like 'PAY-' || to_char(c.day, 'YYYYMMDD') || '-%')`,
    ].join('; '),
  );
}

cardSpec(['payment'], cleanUp);

interface Books {
  method: { id: string; name: string; is_active: boolean };
  payment: { id: string; reference: string; status: string };
}

/** A method with its account and a draft payment from it, every datum that could name them filled. */
async function someBooks(context: BrowserContext): Promise<Books> {
  const method = await post<Books['method']>(context, '/payment/methods', {
    name: `${TAG} BBVA`,
    method_type: 'transfer',
    bank_account_ref: 'ES91 2100 0418 4502 0005 1332',
  });
  const payment = await post<Books['payment']>(context, '/payment/payments', {
    method_id: method.id,
    payment_date: '2026-10-14',
    amount: 1250,
    beneficiary_name: `${TAG} Harinas del Norte`,
    concept: `${TAG} harina`,
    supplier_invoice_ref: 'HN-77',
  });
  return { method, payment };
}

/** The payment and the method as their reads say them now. */
async function asTheyAre(context: BrowserContext, books: Books): Promise<[string, boolean]> {
  const payment = await api<{ status: string }>(context, A, 'GET', `/payment/payments/detail?id=${books.payment.id}`);
  const method = await api<{ is_active: boolean }>(context, A, 'GET', `/payment/methods/detail?id=${books.method.id}`);
  expect([payment.status, method.status]).toEqual([200, 200]);
  return [payment.data.status, method.data.is_active];
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`payment-assistant-card — in ${language}, a write of Payments says which payment and which method, never by an id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const books = await someBooks(context);
    const before = await asTheyAre(context, books);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Cancela el pago PAY-…», a dangerous write: the payment by its reference, titled as the list calls one, in every
    // size.
    const cancelled = await datumOf(page, 'payment__payment__cancel', { id: books.payment.id, reason: `${TAG} duplicado` });
    expect([cancelled.label, cancelled.value]).toEqual([words.payment, books.payment.reference]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.payment}: ${books.payment.reference}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await capture(page, `hub-674-cancel-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Pasa la cuenta BBVA a efectivo»: a write that is not dangerous is said in one line, the method by its name and
    // its new type by the label of the methods form, never as sent.
    const edited = await fieldsOf(page, 'payment__method__update', { id: books.method.id, method_type: 'cash' });
    const said = Object.fromEntries(edited.map((field) => [field.name, [field.label, field.value]]));
    expect([said.id, said.method_type?.[1]]).toEqual([[words.method, books.method.name], words.cash]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(books.method.name);
      await expect(card(page)).toContainText(words.cash);
      await expect(card(page)).not.toContainText('cash', { ignoreCase: false });
      await capture(page, `hub-674-method-update-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // A new payment says the method the money leaves from by its name.
    const leavesFrom = await datumOf(
      page,
      'payment__payment__create',
      { method_id: books.method.id, payment_date: '2026-10-15', amount: 990, beneficiary_name: `${TAG} Otro` },
      'method_id',
    );
    expect([leavesFrom.label, leavesFrom.value]).toEqual([words.method, books.method.name]);
    await expect(card(page)).toContainText(books.method.name);
    await cancel(page);

    // Cancelled, nothing changed: the payment still a draft, the method as it was, and no other payment recorded.
    expect(await asTheyAre(context, books)).toEqual(before);
    expect(psql(`select count(*) from payment_payment where beneficiary_name = '${TAG} Otro'`)).toBe('0');
    await context.close();
  });
}

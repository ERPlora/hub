// PAYMENT-F02 «Registrar un pago»: «New payment» asks for the old panel's Method (only the active ones),
// Date (today), Amount (as a person writes it), Beneficiary and Concept, plus the Beneficiary IBAN and
// the Supplier invoice the old screen left to the API, with «Record payment». The three states of the
// methods read are told apart (the old payments#24): still loading, could not be read (Retry), none
// yet (go to Methods). An amount that is not one, or is 0, is refused under the field without asking
// the server; the server's refusals go under their field (the old pm#513: inside the form).
import { InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { localDay } from '../lib/format';
import type { MethodOut, PaymentOut } from '../operations';
import { click, errorFrame, ionValue, mountPayment, page, RECORDER, settle } from '../__tests__/mount-payment';
import PaymentFormModal from './PaymentFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; placeholder?: string };

const METHODS = 'payment.method.list';
const method = (id: string, name: string): MethodOut => ({
  id,
  name,
  method_type: 'transfer',
  bank_account_ref: '',
  is_active: true,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
});
const BANK = method('m1', 'BBVA account');
const CASH = method('m2', 'Cash drawer');
const CREATED = { id: 'p1', reference: 'PAY-20261014-0001' } as PaymentOut;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountPayment(PaymentFormModal, { props: { open: false }, locale, session: RECORDER });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  await m.live();
  const field = (name: string) => m.inDoc(`payment-form-${name}`) as Control;
  const save = () => m.inDoc('payment-form-submit') as Control;
  const banner = (testid: string) => m.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === testid);
  async function fill(amount = '12,50') {
    await ionValue(field('method'), 'm1', 'ionChange');
    await ionValue(field('amount'), amount, 'ionInput');
    await ionValue(field('beneficiary'), ' Proveedor Norte SL ', 'ionInput');
  }
  return { ...m, field, save, banner, fill };
}

describe('PaymentFormModal', () => {
  it('asks for the old panel’s fields and the two the API had, with today’s date', async () => {
    const s = await setup();
    await s.result(METHODS, page([BANK, CASH]));
    expect(s.params(METHODS)).toEqual([{ is_active: true, limit: 100 }]);
    expect(s.inDoc('payment-form')?.getAttribute('aria-label')).toBe('New payment');
    expect(['method', 'date', 'amount', 'beneficiary', 'concept', 'iban', 'invoice'].map((name) => s.field(name).label)).toEqual([
      'Method',
      'Date',
      'Amount',
      'Beneficiary',
      'Concept',
      'Beneficiary IBAN',
      'Supplier invoice',
    ]);
    expect(s.field('date').value).toBe(localDay());
    expect(s.field('method').placeholder).toBe('Method…');
    expect([...s.field('method').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual([
      'BBVA account',
      'Cash drawer',
    ]);
    expect(s.save().textContent).toContain('Record payment');
    expect(s.save().disabled).toBe(true);
  });

  it('records the payment in cents with the method picked, and closes', async () => {
    const s = await setup();
    await s.result(METHODS, page([BANK, CASH]));
    s.answer(201, CREATED);
    await s.fill();
    await ionValue(s.field('date'), '2026-10-10', 'ionInput');
    await ionValue(s.field('concept'), 'Tintes', 'ionInput');
    await ionValue(s.field('invoice'), 'F-118', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/payment/payments',
        query: {},
        body: {
          method_id: 'm1',
          payment_date: '2026-10-10',
          amount: 1250,
          beneficiary_name: 'Proveedor Norte SL',
          concept: 'Tintes',
          beneficiary_iban: '',
          supplier_invoice_ref: 'F-118',
          idempotency_key: expect.stringMatching(UUID),
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    expect(s.wrapper.emitted('created')).toEqual([[CREATED]]);
  });

  it('the same form sent again carries the same attempt key; the next «New payment» makes a new one (payments#8)', async () => {
    const s = await setup();
    await s.result(METHODS, page([BANK]));
    s.answer(503, { error: { code: 'unavailable', message: 'Try again in a moment.' } });
    await s.fill();
    await click(s.save());
    s.answer(201, CREATED);
    await click(s.save());
    const keys = () => s.sent().map((call) => (call.body as { idempotency_key: string }).idempotency_key);
    expect(keys()).toHaveLength(2);
    expect(keys()[0]).toMatch(UUID);
    expect(keys()[1]).toBe(keys()[0]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);

    await s.wrapper.setProps({ open: true });
    await settle();
    await s.fill();
    await click(s.save());
    expect(keys()).toHaveLength(3);
    expect(keys()[2]).toMatch(UUID);
    expect(keys()[2]).not.toBe(keys()[0]);
  });

  it('an amount that is not one, or is 0, is refused under the field and nothing is sent', async () => {
    const s = await setup();
    await s.result(METHODS, page([BANK]));
    await s.fill('abc');
    await click(s.save());
    expect(s.field('amount').errorText).toBe('This is not an amount. Type a figure, for example 12.50.');
    await ionValue(s.field('amount'), '0', 'ionInput');
    await click(s.save());
    expect(s.field('amount').errorText).toBe('The amount of a payment must be greater than 0.');
    expect(s.sent()).toEqual([]);
  });

  it('a refusal of the server goes under its field, inside the form, and what was typed stays', async () => {
    const s = await setup();
    await s.result(METHODS, page([BANK]));
    const message = 'That IBAN is not valid: check the country, the check digits and the length.';
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { beneficiary_iban: message } } });
    await s.fill();
    await ionValue(s.field('iban'), 'ES00', 'ionInput');
    await click(s.save());
    expect(s.field('iban').errorText).toBe(message);
    expect(s.field('iban').value).toBe('ES00');
    expect(s.wrapper.emitted('update:open')?.at(-1)).not.toEqual([false]);
  });

  it('no active method yet: says so and offers to go to Methods', async () => {
    const s = await setup();
    await s.result(METHODS, page([]));
    expect(s.banner('payment-form-no-methods')?.text()).toContain(
      'No active payment methods yet. Create one in Methods before recording a payment.',
    );
    expect(s.field('method').disabled).toBe(true);
    await click(s.inDoc('payment-form-go-methods'));
    expect(s.router.currentRoute.value.path).toBe('/payment/methods');
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('the methods could not be read: says it, with Retry, and does not pretend there are none', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(METHODS), 'internal_error'));
    await settle();
    expect(s.banner('payment-form-methods-error')?.text()).toContain('Payment methods could not be loaded.');
    expect(s.banner('payment-form-no-methods')).toBeUndefined();
    expect(s.inDoc('payment-form-methods-retry')).not.toBeNull();
  });

  it('while the methods load, the picker waits, with no warning', async () => {
    const s = await setup();
    expect([s.field('method').disabled, s.field('method').placeholder]).toEqual([true, 'Loading…']);
    expect(s.banner('payment-form-no-methods')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.result(METHODS, page([BANK]));
    expect(s.inDoc('payment-form')?.getAttribute('aria-label')).toBe('Nuevo pago');
    expect([s.field('method').label, s.field('amount').label, s.field('invoice').label]).toEqual(['Método', 'Importe', 'Factura del proveedor']);
    expect(s.save().textContent).toContain('Registrar pago');
  });
});

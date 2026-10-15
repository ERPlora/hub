// PAYMENT-F05 «Cancelar un pago»: «Cancel payment» on a row asks for the «Cancellation reason» in a form
// (the old screen used the browser's prompt), named after the payment, with «Cancel payment» in red and
// «Keep it»; it cannot be pressed without a reason. The server's refusal (a payment that finished in the
// meantime) stays in the form.
import { describe, expect, it, vi } from 'vitest';

import type { PaymentOut } from '../operations';
import { click, ionValue, mountPayment, settle } from '../__tests__/mount-payment';
import CancelPaymentModal from './CancelPaymentModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

const PAYMENT = { id: 'p1', reference: 'PAY-20261014-0001', status: 'approved' } as PaymentOut;

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountPayment(CancelPaymentModal, { props: { open: false, payment: PAYMENT }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const reason = () => m.inDoc('payment-cancel-reason') as Control;
  const save = () => m.inDoc('payment-cancel-submit') as Control;
  return { ...m, reason, save };
}

describe('CancelPaymentModal', () => {
  it('asks for the reason, named after the payment, and needs one', async () => {
    const s = await setup();
    expect(s.inDoc('payment-cancel')?.getAttribute('aria-label')).toBe('Cancel payment — PAY-20261014-0001');
    expect(s.reason().label).toBe('Cancellation reason');
    expect(s.save().textContent).toContain('Cancel payment');
    expect(s.inDoc('payment-cancel-cancel')?.textContent).toContain('Keep it');
    expect(s.save().disabled).toBe(true);
    await ionValue(s.reason(), '   ', 'ionInput');
    expect(s.save().disabled).toBe(true);
  });

  it('sends payment.payment.cancel with the reason trimmed, and closes', async () => {
    const s = await setup();
    s.answer(200, { ...PAYMENT, status: 'cancelled', cancel_reason: 'Duplicated' });
    await ionValue(s.reason(), ' Duplicated ', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/payment/payments/cancel', query: {}, body: { id: 'p1', reason: 'Duplicated' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a payment that can no longer be cancelled says so in the form', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'payment.not_cancellable', message: 'This payment can no longer be cancelled.' } });
    await ionValue(s.reason(), 'late', 'ionInput');
    await click(s.save());
    expect(s.inDoc('payment-cancel-error')?.textContent).toContain('This payment can no longer be cancelled.');
    expect(s.reason().value).toBe('late');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('payment-cancel')?.getAttribute('aria-label')).toBe('Cancelar pago — PAY-20261014-0001');
    expect(s.reason().label).toBe('Motivo de cancelación');
    expect(s.inDoc('payment-cancel-cancel')?.textContent).toContain('No cancelar');
  });
});

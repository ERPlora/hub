// CART_CHECKOUT-F10 «Registrar que el pago falló»: «Fail» on a row asks for the «Reason» in a form named
// after the order (the old screen sent «Cancelled by operator», in English, without asking), with «Fail
// order» in red and «Keep it»; it cannot be pressed without a reason. The server's refusal (an order
// completed in the meantime) stays in the form, with the reason typed.
import { describe, expect, it, vi } from 'vitest';

import type { OrderOut } from '../operations';
import { click, ionValue, mountCartCheckout, settle } from '../__tests__/mount-cart-checkout';
import FailOrderModal from './FailOrderModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

const ORDER = { id: 'o1', order_number: 'OS-20261014-0001', status: 'initiated' } as OrderOut;

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCartCheckout(FailOrderModal, { props: { open: false, order: ORDER }, locale, path: '/cart_checkout/orders' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const reason = () => m.inDoc('cart-checkout-fail-reason') as Control;
  const save = () => m.inDoc('cart-checkout-fail-submit') as Control;
  return { ...m, reason, save };
}

describe('FailOrderModal', () => {
  it('asks for the reason, named after the order, and needs one', async () => {
    const s = await setup();
    expect(s.inDoc('cart-checkout-fail')?.getAttribute('aria-label')).toBe('Fail order — OS-20261014-0001');
    expect(s.reason().label).toBe('Reason');
    expect(s.save().textContent).toContain('Fail order');
    expect(s.inDoc('cart-checkout-fail-cancel')?.textContent).toContain('Keep it');
    expect(s.save().disabled).toBe(true);
    await ionValue(s.reason(), '   ', 'ionInput');
    expect(s.save().disabled).toBe(true);
  });

  it('sends cart_checkout.order.fail with the reason trimmed, and closes', async () => {
    const s = await setup();
    s.answer(200, { ...ORDER, status: 'failed', failure_reason: 'Card declined' });
    await ionValue(s.reason(), ' Card declined ', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/cart_checkout/orders/fail', query: {}, body: { order_id: 'o1', reason: 'Card declined' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('an order that can no longer fail says so in the form, and the reason stays', async () => {
    const s = await setup();
    const message = 'Only an initiated or paid order can fail; this one is Completed.';
    s.answer(409, { error: { code: 'cart_checkout.invalid_transition', message } });
    await ionValue(s.reason(), 'late', 'ionInput');
    await click(s.save());
    expect(s.inDoc('cart-checkout-fail-error')?.textContent).toContain(message);
    expect(s.reason().value).toBe('late');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('cart-checkout-fail')?.getAttribute('aria-label')).toBe('Fallar pedido — OS-20261014-0001');
    expect(s.reason().label).toBe('Motivo');
    expect(s.inDoc('cart-checkout-fail-cancel')?.textContent).toContain('Mantener');
  });
});

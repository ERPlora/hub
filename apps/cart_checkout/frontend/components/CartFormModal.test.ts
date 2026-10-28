// CART_CHECKOUT-F01 «Crear un carrito»: «New cart» asks for Session (required: «Save» stays off without
// it), Email and Name, with the old panel's placeholders, and sends `cart_checkout.cart.create` without a
// currency (the server gives the business's one: the old cart_checkout#32 sent a literal EUR). A session
// another cart has (409) or an email that is not one (422) goes under its field, and what was typed stays
// (the old form-error-in-panel: the refusal travels with the form, never under it).
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountCartCheckout, settle } from '../__tests__/mount-cart-checkout';
import CartFormModal from './CartFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; placeholder?: string };

const CART = {
  id: 'c1',
  session_token: 'sess_x9',
  customer_email: 'ana@example.com',
  customer_name: 'Ana García',
  status: 'active',
  total_items: '0.000',
  total_amount: 0,
  currency: 'EUR',
  currency_decimals: 2,
};

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCartCheckout(CartFormModal, { props: { open: false }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`cart-checkout-cart-form-${name}`) as Control;
  const save = () => m.inDoc('cart-checkout-cart-form-submit') as Control;
  return { ...m, field, save };
}

describe('CartFormModal', () => {
  it('asks for Session, Email and Name with the old placeholders; Save needs a session', async () => {
    const s = await setup();
    expect(s.inDoc('cart-checkout-cart-form')?.getAttribute('aria-label')).toBe('New cart');
    expect([s.field('session').label, s.field('email').label, s.field('name').label]).toEqual(['Session', 'Email', 'Name']);
    expect([s.field('session').placeholder, s.field('email').placeholder, s.field('name').placeholder]).toEqual([
      'sess_a1b2c3',
      'customer@example.com',
      'John Doe',
    ]);
    expect(s.save().textContent).toContain('Save');
    expect(s.save().disabled).toBe(true);
    await ionValue(s.field('session'), '   ', 'ionInput');
    expect(s.save().disabled).toBe(true);
  });

  it('sends cart_checkout.cart.create trimmed, without a currency, tells the page and closes', async () => {
    const s = await setup();
    s.answer(201, CART);
    await ionValue(s.field('session'), ' sess_x9 ', 'ionInput');
    await ionValue(s.field('email'), ' ana@example.com ', 'ionInput');
    await ionValue(s.field('name'), 'Ana García', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/cart_checkout/carts',
        query: {},
        body: { session_token: 'sess_x9', customer_email: 'ana@example.com', customer_name: 'Ana García' },
      },
    ]);
    expect(s.wrapper.emitted('created')?.at(-1)).toEqual([CART]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a session another cart has goes under Session, and what was typed stays', async () => {
    const s = await setup();
    const message = 'There is already a cart with that session.';
    s.answer(409, { error: { code: 'cart_checkout.session_taken', message, fields: { session_token: message } } });
    await ionValue(s.field('session'), 'sess_1', 'ionInput');
    await click(s.save());
    expect(s.field('session').errorText).toBe(message);
    expect(s.field('session').value).toBe('sess_1');
    expect(s.wrapper.emitted('update:open')?.at(-1)).not.toEqual([false]);
  });

  it('an email that is not one goes under Email', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'invalid_field', message: 'Enter a valid email.', fields: { customer_email: 'Enter a valid email.' } } });
    await ionValue(s.field('session'), 'sess_1', 'ionInput');
    await ionValue(s.field('email'), 'ana', 'ionInput');
    await click(s.save());
    expect(s.field('email').errorText).toBe('Enter a valid email.');
  });

  it('opens empty again after a save', async () => {
    const s = await setup();
    s.answer(201, CART);
    await ionValue(s.field('session'), 'sess_x9', 'ionInput');
    await click(s.save());
    await s.wrapper.setProps({ open: true });
    await settle();
    expect(s.field('session').value).toBe('');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('cart-checkout-cart-form')?.getAttribute('aria-label')).toBe('Nuevo carrito');
    expect([s.field('session').label, s.field('email').label, s.field('name').label]).toEqual(['Sesión', 'Email', 'Nombre']);
    expect([s.field('email').placeholder, s.field('name').placeholder]).toEqual(['cliente@ejemplo.com', 'Ana García']);
    expect(s.save().textContent).toContain('Guardar');
  });
});

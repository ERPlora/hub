// The foot of the charge sheet (SALE-F01–F06): one button that says what it does and for how much —
// «Charge €42.50», «Charge €42.50 by card», «Charging…» while it goes —; when it cannot charge yet, the
// reason written above it and its short form on the button, which stays tappable and answers; a refusal
// in the server's words; a lost answer said as such, with «Check in Sales» when nobody knows.
import { HubIcon } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import type { ChargeBlock } from '../../lib/checkout/blocks';
import type { TenderMethod } from '../../lib/checkout/tender';
import { plain } from '../../lib/format';
import CheckoutFoot from './CheckoutFoot.vue';

type Button = HTMLElement & { disabled?: boolean; expand?: string };

const CASH: TenderMethod = { id: 'm-cash', display_name: 'Cash', type: 'cash', requires_change: true };
const CARD: TenderMethod = { id: 'm-card', display_name: 'Card', type: 'card', requires_change: false };
const BIZUM: TenderMethod = { id: 'm-bizum', display_name: 'Bizum', type: 'other', requires_change: false };

const BASE = { total: 4250, method: CASH, split: false, block: null, busy: false, ready: true, failure: null };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(CheckoutFoot, { props: { ...BASE, ...props }, locale });
  const confirm = () => m.find('sale-checkout-confirm').element as Button;
  const label = () => plain(confirm().textContent ?? '').trim();
  const reason = () => m.find('sale-checkout-block-reason');
  const error = () => m.find('sale-checkout-error');
  return { ...m, confirm, label, reason, error };
}

const block = (b: ChargeBlock) => ({ block: b });

describe('CheckoutFoot: the button', () => {
  it('says what it charges: cash and split «Charge €42.50», a card «by card», another method by name', async () => {
    expect((await setup()).label()).toBe('Charge €42.50');
    expect((await setup({ method: CARD, split: true })).label()).toBe('Charge €42.50');
    expect((await setup({ method: CARD })).label()).toBe('Charge €42.50 by card');
    expect((await setup({ method: BIZUM })).label()).toBe('Charge €42.50 with Bizum');
  });

  it('is the sheet’s full-width primary button and charges on tap', async () => {
    const s = await setup();
    expect([s.confirm().expand, s.confirm().disabled, s.confirm().getAttribute('aria-disabled')]).toEqual(['block', false, null]);
    await click(s.confirm());
    expect(s.wrapper.emitted('confirm')).toEqual([[]]);
  });

  it('while the total loads it says «Charge» and cannot be pressed', async () => {
    const s = await setup({ total: undefined, ready: false });
    expect([s.label(), s.confirm().disabled]).toEqual(['Charge', true]);
    await click(s.confirm());
    expect(s.wrapper.emitted('confirm')).toBeUndefined();
  });

  it('while charging: «Charging…», natively disabled, a spinner', async () => {
    const s = await setup({ busy: true });
    expect([s.label(), s.confirm().disabled]).toEqual(['Charging…', true]);
    expect(s.find('sale-checkout-confirm').find('ion-spinner').exists()).toBe(true);
    await click(s.confirm());
    expect(s.wrapper.emitted('confirm')).toBeUndefined();
  });
});

describe('CheckoutFoot: why it cannot charge', () => {
  it('cash with nothing typed: the reason above, and the button keeps the amount', async () => {
    const s = await setup(block({ kind: 'tenderedMissing' }));
    expect(s.reason().text()).toBe('Enter the amount tendered on the keypad');
    expect([s.label(), s.confirm().getAttribute('aria-disabled'), s.confirm().disabled]).toEqual(['Charge €42.50', 'true', false]);
  });

  it('a tap on a blocked button answers with the reason instead of charging', async () => {
    const s = await setup(block({ kind: 'tenderedShort' }));
    await click(s.confirm());
    expect(s.wrapper.emitted('confirm')).toBeUndefined();
    expect(s.wrapper.emitted('blocked')).toEqual([[{ kind: 'tenderedShort' }, 'The amount tendered does not cover the total']]);
  });

  it('says each reason, short on the button and whole above it', async () => {
    const cases: [ChargeBlock, string, string | null][] = [
      [{ kind: 'tenderedShort' }, 'The amount tendered does not cover the total', 'The amount tendered does not cover the total'],
      [{ kind: 'remaining', amount: 2250 }, '€22.50 still to cover', '€22.50 still to cover before the sale can be charged.'],
      [{ kind: 'cashLimit', limit: 100000 }, 'Cash not allowed', 'The law does not allow cash for sales of €1,000.00 or more. Charge it by card or Bizum.'],
      [{ kind: 'recipient' }, "Enter the customer's details", null],
      [{ kind: 'customerRequired' }, 'Customer required', 'This business requires a customer on every sale. Choose one to carry on with the charge.'],
    ];
    for (const [b, short, whole] of cases) {
      const s = await setup(block(b));
      expect(s.label(), b.kind).toBe(short);
      expect(s.reason().exists() ? plain(s.reason().text()) : null, b.kind).toBe(whole);
    }
  });

  it('the recipient block is answered with its short form (the details box already explains it)', async () => {
    const s = await setup(block({ kind: 'recipient' }));
    await click(s.confirm());
    expect(s.wrapper.emitted('blocked')).toEqual([[{ kind: 'recipient' }, "Enter the customer's details"]]);
  });
});

describe('CheckoutFoot: what happened', () => {
  it('a refusal in the server’s words', async () => {
    const s = await setup({ failure: { kind: 'refused', code: 'sale.order_changed', message: 'The check changed while it was being charged.' } });
    expect([s.error().text(), s.error().attributes('role')]).toEqual(['The check changed while it was being charged.', 'alert']);
    expect(s.find('sale-checkout-check-sales').exists()).toBe(false);
  });

  it('not charged: the server is not answering', async () => {
    const s = await setup({ failure: { kind: 'not_charged' } });
    expect(s.error().text()).toBe(
      "The server isn't responding (it may be restarting). Try again in a few seconds and, if it keeps happening, call the manager.",
    );
  });

  it('unknown: check it in Sales before charging again, with the outline button that goes there', async () => {
    const s = await setup({ failure: { kind: 'unknown' } });
    expect(s.error().text()).toBe("We couldn't confirm whether this charge went through. Check it in Sales before charging again.");
    const go = s.find('sale-checkout-check-sales');
    expect([go.text(), (go.element as HTMLElement & { fill?: string }).fill, go.findComponent(HubIcon).props('name')]).toEqual(['Check in Sales', 'outline', 'ion:cart-outline']);
    await click(go.element);
    expect(s.wrapper.emitted('checkSales')).toEqual([[]]);
  });
});

describe('CheckoutFoot: Spanish', () => {
  it('uses the old words', async () => {
    expect((await setup({}, 'es')).label()).toBe('Cobrar 42,50 €');
    expect((await setup({ method: CARD }, 'es')).label()).toBe('Cobrar 42,50 € con tarjeta');
    expect((await setup({ busy: true }, 'es')).label()).toBe('Cobrando…');
    expect((await setup(block({ kind: 'remaining', amount: 2250 }), 'es')).label()).toBe('Faltan 22,50 €');
    expect((await setup(block({ kind: 'recipient' }), 'es')).label()).toBe('Faltan los datos del cliente');
    expect((await setup(block({ kind: 'tenderedMissing' }), 'es')).reason().text()).toBe('Marca en el teclado el importe entregado');
    expect((await setup(block({ kind: 'tenderedShort' }), 'es')).label()).toBe('Lo entregado no cubre el total');
    const unknown = await setup({ failure: { kind: 'unknown' } }, 'es');
    expect(unknown.error().text()).toBe('No hemos podido confirmar si el cobro se completó. Compruébalo en Ventas antes de volver a cobrar.');
    expect(unknown.find('sale-checkout-check-sales').text()).toBe('Comprobar en Ventas');
    expect((await setup({ failure: { kind: 'not_charged' } }, 'es')).error().text()).toBe(
      'El servidor no responde (puede estar reiniciándose). Inténtalo de nuevo en unos segundos y, si persiste, avisa al encargado.',
    );
  });
});

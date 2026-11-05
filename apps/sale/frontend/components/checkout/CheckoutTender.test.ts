// The tender group of the charge sheet (SALE-F01, F02, F03): the methods (only when there is more than
// one), then cash: «Tendered», the row that asks for the amount and then says the big «Change», and the
// keypad; another method: «Exact amount» and
// «Charge <amount> on the card terminal, then confirm.»; «Split the payment», and once splitting «Amount
// for this payment» (or «Tendered» in cash), «Add this payment» while something is left, and «Payments
// taken». It paints and sends; the state is the sheet's (useTender).
import { HubIcon } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import type { Leg } from '../../lib/checkout/tender';
import { plain } from '../../lib/format';
import type { PaymentMethodOut } from '../../operations';
import CheckoutTender from './CheckoutTender.vue';
import MethodPicker from './MethodPicker.vue';
import PayKeypad from './PayKeypad.vue';
import TenderList from './TenderList.vue';

const method = (id: string, type: PaymentMethodOut['type'], display_name: string): PaymentMethodOut => ({
  id,
  name: id,
  display_name,
  type,
  sort_order: 0,
  requires_change: type === 'cash',
  allowed: true,
});
const CASH = method('m-cash', 'cash', 'Cash');
const CARD = method('m-card', 'card', 'Card');

const BASE = { methods: [CASH, CARD], method: CASH, cashOff: false, splitting: false, legs: [], typed: 0, change: 0, total: 4250, remaining: 4250, block: null };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(CheckoutTender, { props: { ...BASE, ...props }, locale });
  await m.live();
  const text = (testid: string) => plain(m.find(testid).text()).replace(/\s+/g, ' ').trim();
  const parts = (testid: string) => m.find(testid).findAll('span').map((p) => plain(p.text()));
  return { ...m, text, parts };
}

describe('CheckoutTender: one method', () => {
  it('cash: the methods, «Tendered» and the keypad; no change until there is some', async () => {
    const s = await setup({ typed: 2000 });
    expect(s.wrapper.findComponent(MethodPicker).props()).toMatchObject({ selectedId: 'm-cash', cashOff: false });
    expect(s.parts('sale-checkout-tendered')).toEqual(['Tendered', '€20.00']);
    expect(s.find('sale-checkout-change').exists()).toBe(false);
    expect(s.wrapper.findComponent(PayKeypad).exists()).toBe(true);
    expect(s.find('sale-checkout-exact').exists()).toBe(false);
  });

  it('cash: the change, big', async () => {
    const s = await setup({ typed: 5000, change: 750 });
    expect(s.parts('sale-checkout-change')).toEqual(['Change', '€7.50']);
  });

  it('cash: the row over the keypad asks for the amount, then says it falls short, then the change takes its place', async () => {
    const missing = await setup({ block: { kind: 'tenderedMissing' } });
    expect(missing.text('sale-checkout-block-reason')).toBe('Enter the amount tendered on the keypad');
    const short = await setup({ typed: 100, block: { kind: 'tenderedShort' } });
    expect(short.text('sale-checkout-block-reason')).toBe('The amount tendered does not cover the total');
    expect(short.find('sale-checkout-change').exists()).toBe(false);
    const covered = await setup({ typed: 5000, change: 750 });
    expect(covered.find('sale-checkout-block-reason').exists()).toBe(false);
    expect(covered.find('sale-checkout-tender-status').find('[data-testid="sale-checkout-change"]').exists()).toBe(true);
  });

  it('hub#456: the row is there with nothing to say, before the keypad, so the change never pushes the keys', async () => {
    const s = await setup({ block: null, change: 0 });
    const row = s.find('sale-checkout-tender-status').element;
    expect(row.textContent?.trim()).toBe('');
    const keypad = s.find('sale-checkout-keypad').element;
    expect(row.compareDocumentPosition(keypad) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('a reason its keys do not change stays in the foot', async () => {
    const s = await setup({ block: { kind: 'customerRequired' } });
    expect(s.find('sale-checkout-block-reason').exists()).toBe(false);
  });

  it('another method: «Exact amount» and the card terminal hint, no keypad', async () => {
    const s = await setup({ method: CARD });
    expect(s.parts('sale-checkout-exact')).toEqual(['Exact amount', '€42.50']);
    expect(s.text('sale-checkout-hint')).toBe('Charge €42.50 on the card terminal, then confirm.');
    expect(s.wrapper.findComponent(PayKeypad).exists()).toBe(false);
    expect(s.find('sale-checkout-tender-status').exists()).toBe(false);
  });

  it('a single method is not offered as a choice', async () => {
    const s = await setup({ methods: [CASH] });
    expect(s.wrapper.findComponent(MethodPicker).exists()).toBe(false);
  });

  it('offers «Split the payment», and sends the method, the keys and the split', async () => {
    const s = await setup();
    expect(s.text('sale-checkout-split')).toBe('Split the payment');
    expect(s.find('sale-checkout-split').findComponent(HubIcon).props('name')).toBe('ion:swap-horizontal-outline');
    s.wrapper.findComponent(MethodPicker).vm.$emit('pick', CARD);
    s.wrapper.findComponent(PayKeypad).vm.$emit('key', '7');
    await click(s.find('sale-checkout-split').element);
    expect([s.wrapper.emitted('pick'), s.wrapper.emitted('key'), s.wrapper.emitted('split')]).toEqual([[[CARD]], [['7']], [[]]]);
  });

  it('nothing to split on a check worth nothing', async () => {
    const s = await setup({ total: 0, remaining: 0 });
    expect(s.find('sale-checkout-split').exists()).toBe(false);
  });
});

describe('CheckoutTender: split', () => {
  const LEGS: Leg[] = [{ id: 'leg-1', method: CARD, amount: 2000, tendered: 2000 }];

  it('another method types «Amount for this payment» on the keypad; «Add this payment» takes it', async () => {
    const s = await setup({ splitting: true, method: CARD, typed: 1000, legs: LEGS, remaining: 2250 });
    expect(s.parts('sale-checkout-tendered')).toEqual(['Amount for this payment', '€10.00']);
    expect(s.wrapper.findComponent(PayKeypad).exists()).toBe(true);
    expect(s.find('sale-checkout-split').exists()).toBe(false);
    expect(s.text('sale-checkout-add-leg')).toBe('Add this payment');
    await click(s.find('sale-checkout-add-leg').element);
    expect(s.wrapper.emitted('add')).toEqual([[]]);
  });

  it('cash types what was handed over', async () => {
    const s = await setup({ splitting: true, typed: 3000, change: 750, legs: LEGS, remaining: 2250 });
    expect(s.parts('sale-checkout-tendered')).toEqual(['Tendered', '€30.00']);
    expect(s.parts('sale-checkout-change')).toEqual(['Change', '€7.50']);
  });

  it('a leg of another method never gives change: no room kept, unless an earlier cash leg gave some', async () => {
    const card = await setup({ splitting: true, method: CARD, legs: LEGS, remaining: 2250 });
    expect(card.find('sale-checkout-tender-status').exists()).toBe(false);
    const earlier = await setup({ splitting: true, method: CARD, change: 750, legs: LEGS, remaining: 0 });
    expect(earlier.parts('sale-checkout-change')).toEqual(['Change', '€7.50']);
  });

  it('lists the payments taken and passes on their edit and removal', async () => {
    const s = await setup({ splitting: true, legs: LEGS, remaining: 2250 });
    const list = s.wrapper.findComponent(TenderList);
    expect(list.props('legs')).toEqual(LEGS);
    list.vm.$emit('edit', 'leg-1');
    list.vm.$emit('remove', 'leg-1');
    expect([s.wrapper.emitted('edit'), s.wrapper.emitted('remove')]).toEqual([[['leg-1']], [['leg-1']]]);
  });

  it('nothing left to add once covered', async () => {
    const s = await setup({ splitting: true, legs: LEGS, remaining: 0 });
    expect(s.find('sale-checkout-add-leg').exists()).toBe(false);
  });
});

describe('CheckoutTender: Spanish', () => {
  it('uses the old words', async () => {
    const s = await setup({ typed: 5000, change: 750 }, 'es');
    expect(s.parts('sale-checkout-tendered')).toEqual(['Entregado', '50,00 €']);
    expect(s.parts('sale-checkout-change')).toEqual(['Cambio', '7,50 €']);
    expect(s.text('sale-checkout-split')).toBe('Repartir el cobro');
    expect((await setup({ block: { kind: 'tenderedMissing' } }, 'es')).text('sale-checkout-block-reason')).toBe('Marca en el teclado el importe entregado');
    expect((await setup({ block: { kind: 'tenderedShort' } }, 'es')).text('sale-checkout-block-reason')).toBe('Lo entregado no cubre el total');
    const card = await setup({ method: CARD }, 'es');
    expect(card.parts('sale-checkout-exact')).toEqual(['Importe exacto', '42,50 €']);
    expect(card.text('sale-checkout-hint')).toBe('Cobra 42,50 € en el datáfono y confirma.');
    const split = await setup({ splitting: true, method: CARD }, 'es');
    expect(split.parts('sale-checkout-tendered')[0]).toBe('Importe de este cobro');
    expect(split.text('sale-checkout-add-leg')).toBe('Añadir este cobro');
  });
});

// The tender state of the charge sheet (SALE-F01, F02, F03): the method (cash first, or the first that
// can charge over the cash limit), the keypad, the change, «Split the payment» with its legs (add, edit,
// remove) and the `payments` it sends. The total and the cash limit are the server's.
import { describe, expect, it } from 'vitest';
import { effectScope, ref } from 'vue';

import type { PaymentMethodOut } from '../../operations';
import { useTender } from './useTender';

const method = (id: string, type: PaymentMethodOut['type']): PaymentMethodOut => ({
  id,
  name: id,
  display_name: id,
  type,
  sort_order: 0,
  requires_change: type === 'cash',
  allowed: true,
});
const CASH = method('cash', 'cash');
const CARD = method('card', 'card');

function setup(total: number | undefined = 4250, cashLimit: number | null = 100000, decimals = 2) {
  const totalRef = ref(total);
  const methods = ref<PaymentMethodOut[]>([CASH, CARD]);
  const limit = ref(cashLimit);
  const scope = effectScope();
  const tender = scope.run(() => useTender({ total: totalRef, methods, cashLimit: limit, decimals: () => decimals }))!;
  const type = (...keys: string[]) => keys.forEach((k) => tender.press(k));
  return { tender, totalRef, methods, limit, type };
}

describe('useTender: one method', () => {
  it('starts on cash with nothing typed', () => {
    const { tender } = setup();
    expect([tender.method.value?.id, tender.typed.value, tender.splitting.value, tender.legs.value]).toEqual(['cash', 0, false, []]);
  });

  it('types what was handed over and gives the change', () => {
    const { tender, type } = setup();
    type('5', '0');
    expect([tender.typed.value, tender.change.value]).toEqual([5000, 750]);
    type('C');
    expect([tender.typed.value, tender.change.value]).toEqual([0, 0]);
  });

  it('picking another method clears what was typed', () => {
    const { tender, type } = setup();
    type('5', '0');
    expect(tender.pick(CARD)).toBe(true);
    expect([tender.method.value?.id, tender.typed.value]).toEqual(['card', 0]);
  });

  it('the limit looks at the whole operation: a part under it of a check over it refuses cash (Ley 7/2012 art. 7)', () => {
    const totalRef = ref<number | undefined>(50000);
    const scope = effectScope();
    const tender = scope.run(() =>
      useTender({ total: totalRef, operationTotal: () => 120000, methods: [CASH, CARD], cashLimit: 100000, decimals: 2 }),
    )!;
    expect(tender.cashOff.value).toBe(true);
    expect(tender.method.value?.id).toBe('card');
    expect(tender.pick(CASH)).toBe(false);
  });

  it('over the cash limit it starts on card and refuses cash', () => {
    const { tender } = setup(150000);
    expect(tender.cashOff.value).toBe(true);
    expect(tender.method.value?.id).toBe('card');
    expect(tender.pick(CASH)).toBe(false);
    expect(tender.method.value?.id).toBe('card');
  });

  it('a method that stops being offered falls back to the first one', () => {
    const { tender, methods } = setup();
    tender.pick(CARD);
    methods.value = [CASH];
    expect(tender.method.value?.id).toBe('cash');
  });

  it('pays with the method and what was typed', () => {
    const { tender, type } = setup();
    type('5', '0');
    expect(tender.payments()).toEqual([{ method_id: 'cash', tendered: 5000 }]);
    tender.pick(CARD);
    expect(tender.payments()).toEqual([{ method_id: 'card' }]);
  });
});

describe('useTender: split', () => {
  it('opens only with something to pay', () => {
    const zero = setup(0);
    zero.tender.startSplit();
    expect(zero.tender.splitting.value).toBe(false);
    const { tender } = setup();
    tender.startSplit();
    expect([tender.splitting.value, tender.remaining.value]).toEqual([true, 4250]);
  });

  it('a leg takes what was typed, then one with nothing typed covers the rest', () => {
    const { tender, type } = setup();
    tender.startSplit();
    tender.pick(CARD);
    type('2', '0');
    tender.addLeg();
    expect([tender.legs.value.map((l) => [l.method.id, l.amount, l.tendered]), tender.remaining.value, tender.typed.value]).toEqual([
      [['card', 2000, 2000]],
      2250,
      0,
    ]);
    tender.pick(CASH);
    tender.addLeg();
    expect([tender.legs.value.map((l) => [l.method.id, l.amount]), tender.remaining.value]).toEqual([
      [
        ['card', 2000],
        ['cash', 2250],
      ],
      0,
    ]);
    expect(tender.payments()).toEqual([
      { method_id: 'card', amount: 2000 },
      { method_id: 'cash', amount: 2250 },
    ]);
  });

  it('keeps the method chosen for the next leg; nothing to add once covered', () => {
    const { tender } = setup();
    tender.startSplit();
    tender.pick(CARD);
    tender.addLeg();
    expect(tender.method.value?.id).toBe('card');
    tender.addLeg();
    expect(tender.legs.value).toHaveLength(1);
  });

  it('shows the change of cash handed over before the leg is taken, and keeps it after', () => {
    const { tender, type } = setup();
    tender.startSplit();
    type('5', '0');
    expect(tender.change.value).toBe(750);
    tender.addLeg();
    expect([tender.legs.value[0].amount, tender.legs.value[0].tendered, tender.change.value]).toEqual([4250, 5000, 750]);
    expect(tender.payments()).toEqual([{ method_id: 'cash', amount: 4250, tendered: 5000 }]);
  });

  it('edits a leg: back to the keypad with its method and amount, the next key replacing it', () => {
    const { tender, type } = setup();
    tender.startSplit();
    tender.pick(CARD);
    type('2', '0');
    tender.addLeg();
    tender.pick(CASH);
    tender.editLeg(tender.legs.value[0].id);
    expect([tender.legs.value, tender.method.value?.id, tender.typed.value, tender.remaining.value]).toEqual([[], 'card', 2000, 4250]);
    type('3');
    expect(tender.typed.value).toBe(300);
  });

  it('removes a leg: its amount goes back to what is left', () => {
    const { tender } = setup();
    tender.startSplit();
    tender.pick(CARD);
    tender.addLeg();
    tender.removeLeg(tender.legs.value[0].id);
    expect([tender.legs.value, tender.remaining.value]).toEqual([[], 4250]);
  });
});

describe('useTender: the business’s currency (flow business-currency)', () => {
  it('types yen as yen: no decimals, no separator, and the change in yen', () => {
    const { tender, type } = setup(4250, null, 0);
    type('5', '.', '0', '0', '0');
    expect([tender.typed.value, tender.change.value]).toEqual([5000, 750]);
  });

  it('a leg brought back to the keypad keeps its yen', () => {
    const { tender, type } = setup(4250, null, 0);
    tender.startSplit();
    type('1', '0', '0', '0');
    tender.addLeg();
    tender.editLeg(tender.legs.value[0].id);
    expect(tender.typed.value).toBe(1000);
  });
});

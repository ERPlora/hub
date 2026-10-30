// BASE-G98: the Home writes its amounts in the business's currency, as `base.business.get` says it (its country's,
// with its decimals): followed live, one subscription for the whole tab however many pieces ask, and unknown — never
// the euro by default — until the business answers or when its read fails.
// base-money-thousands-grouping: and the platform writes every amount one way, its thousands grouped from four digits
// on («1.234,56 €», as Sales, Payments and every Spanish ERP do; hub#1090), never «1234,56 €» beside it.
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { business, errorFrame, flush, mountBase, POLISH, subId } from '../__tests__/mount-base';
import { formatMoney, useBusinessMoney } from './money';

const EUR = { currency: 'EUR', decimals: 2 };

describe('formatMoney: one way to write an amount in the whole Hub (base-money-thousands-grouping)', () => {
  it('groups the thousands from four digits on, in Spanish too (its CLDR waits for five)', () => {
    expect(formatMoney(123456, 'es', EUR)).toBe('1.234,56 €');
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(formatMoney(1234567, 'es', EUR)).toBe('12.345,67 €');
    expect(formatMoney(123456789, 'es', EUR)).toBe('1.234.567,89 €');
    expect(formatMoney(99999, 'es', EUR)).toBe('999,99 €');
  });

  it('writes a negative amount and zero with the same grouping', () => {
    expect(formatMoney(-123456, 'es', EUR)).toBe('-1.234,56 €');
    expect(formatMoney(-123456, 'en', EUR)).toBe('-€1,234.56');
    expect(formatMoney(0, 'es', EUR)).toBe('0,00 €');
  });

  it("takes the amount in its currency's minor unit, with that currency's decimals and the symbol a till prints", () => {
    expect(formatMoney(123400, 'es', { currency: 'JPY', decimals: 0 })).toBe('123.400 ¥');
    expect(formatMoney(123400, 'en', { currency: 'JPY', decimals: 0 })).toBe('¥123,400');
    expect(formatMoney(123456, 'es', { currency: 'KWD', decimals: 3 })).toBe('123,456 KWD');
    // A currency other than the business's: its narrow symbol, as the screens that group already write it.
    expect(formatMoney(123456, 'es', { currency: 'USD', decimals: 2 })).toBe('1.234,56 $');
    expect(formatMoney(123456, 'es', { currency: 'PLN', decimals: 2 })).toBe('1.234,56 zł');
  });

  it('until the currency is known, the figure alone (grouped, two decimals), never in the euro by default', () => {
    expect(formatMoney(123456, 'es')).toBe('1.234,56');
    expect(formatMoney(123456, 'en')).toBe('1,234.56');
  });

  it('nothing to show is «—», and a locale Intl does not know falls back to English', () => {
    expect(formatMoney(null, 'es', EUR)).toBe('—');
    expect(formatMoney(undefined, 'es', EUR)).toBe('—');
    expect(formatMoney(Number.NaN, 'es', EUR)).toBe('—');
    expect(formatMoney(123456, '!!', EUR)).toBe('€1,234.56');
  });

  it('one format per currency: a business that follows another on the same page keeps its own', () => {
    expect(formatMoney(500, 'es', { currency: 'PLN', decimals: 2 })).toBe('5,00 zł');
    expect(formatMoney(500, 'es', EUR)).toBe('5,00 €');
    expect(formatMoney(500, 'es', { currency: 'JPY', decimals: 0 })).toBe('500 ¥');
  });
});

/** `pieces` pieces of one screen, each asking for the business's currency. */
const Probe = defineComponent({
  props: { pieces: { type: Number, default: 1 } },
  setup(props) {
    const moneys = Array.from({ length: props.pieces }, () => useBusinessMoney());
    return () => h('div', moneys.map((money) => h('span', { 'data-testid': 'money' }, JSON.stringify(money.value ?? null))));
  },
});

const read = (wrapper: { findAll: (s: string) => { text: () => string }[] }) =>
  wrapper.findAll('[data-testid="money"]').map((probe) => JSON.parse(probe.text()));

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useBusinessMoney', () => {
  it("is the business's currency and decimals, unknown until it answers, and follows each change live", async () => {
    const m = await mountBase(Probe);
    const call = await m.live();
    expect(m.client.stream.subscriptions('base.business.get').map((sub) => sub.params)).toEqual([{}]);
    expect(read(m.wrapper)).toEqual([null]);
    await m.result(call, 'base.business.get', business(POLISH));
    expect(read(m.wrapper)).toEqual([{ currency: 'PLN', decimals: 2 }]);
    await m.result(call, 'base.business.get', business({ currency: 'JPY', currency_decimals: 0 }), 2);
    expect(read(m.wrapper)).toEqual([{ currency: 'JPY', decimals: 0 }]);
  });

  it('every piece of the tab shares one subscription', async () => {
    const m = await mountBase(Probe, { props: { pieces: 2 } });
    const call = await m.live();
    expect(m.client.stream.subscriptions('base.business.get')).toHaveLength(1);
    await m.result(call, 'base.business.get', business());
    expect(read(m.wrapper)).toEqual([
      { currency: 'EUR', decimals: 2 },
      { currency: 'EUR', decimals: 2 },
    ]);
  });

  it('a failed read leaves it unknown, never a currency it did not get', async () => {
    const m = await mountBase(Probe);
    const call = await m.live();
    call.push(errorFrame(subId(m.client, 'base.business.get'), 'internal'));
    await flush();
    expect(read(m.wrapper)).toEqual([null]);
  });
});

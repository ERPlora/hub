// BASE-G98: the Home writes its amounts in the business's currency, as `base.business.get` says it (its country's,
// with its decimals): followed live, one subscription for the whole tab however many pieces ask, and unknown — never
// the euro by default — until the business answers or when its read fails.
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { business, errorFrame, flush, mountBase, POLISH, subId } from '../__tests__/mount-base';
import { useBusinessMoney } from './money';

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

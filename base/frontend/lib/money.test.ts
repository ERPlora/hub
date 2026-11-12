// BASE-G98: the Home writes its amounts in the business's currency, as `base.business.get` says it (its country's,
// with its decimals): followed live, one subscription for the whole tab however many pieces ask, and unknown — never
// the euro by default — until the business answers or when its read fails.
import { createShellI18n } from '@erplora/ui/shell';
import { afterEach, describe, expect, expectTypeOf, it } from 'vitest';
import { defineComponent, h } from 'vue';

import moneyFieldEn from '../../../packages/ui/src/components/MoneyInput/locales/en.json';
import moneyFieldEs from '../../../packages/ui/src/components/MoneyInput/locales/es.json';
import { business, errorFrame, flush, mountBase, POLISH, subId } from '../__tests__/mount-base';
import en from '../locale/en.json';
import es from '../locale/es.json';
import { amountFilterErrors, filterCents, formatMoney, useBusinessMoney, useBusinessMoneyRead } from './money';

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

describe('formatMoney', () => {
  it('writes minor units with their thousands grouped, or a dash while the currency is unknown', () => {
    expect(formatMoney(123456, 'es', { currency: 'EUR', decimals: 2 })).toMatch(/^1\.234,56\s€$/);
    expect(formatMoney(1500, 'es', { currency: 'JPY', decimals: 0 })).toMatch(/^1\.500\s¥$/);
    expect(formatMoney(123456, 'es')).toBe('—');
  });

  it('only takes a number: an amount that may be missing does not compile', () => {
    expectTypeOf(formatMoney).parameter(0).toEqualTypeOf<number>();
  });
});

// hub#924: an amount end of a table filter (Payments, Services) is read like the money field, in the business's money;
// one it cannot read does not filter, never «from 0».
describe('filterCents', () => {
  it('reads a typed end in the money, its symbol included, and leaves out what is empty, not an amount or negative', () => {
    const PLN = { currency: 'PLN', decimals: 2 };
    const JPY = { currency: 'JPY', decimals: 0 };
    expect(['12,50 zł', '1.234,5', '', undefined, 'doce', '-5', '13,50 €', '1.250'].map((typed) => filterCents(typed, PLN))).toEqual([
      1250,
      123450,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
    ]);
    expect([filterCents('¥1500', JPY), filterCents('1500', undefined), filterCents('¥1500', undefined)]).toEqual([1500, 150000, undefined]);
  });

  it('reads a minus only on a signed end (a difference): «-5» is −5 € there and no bound elsewhere (hub#1196)', () => {
    const EUR = { currency: 'EUR', decimals: 2 };
    expect([filterCents('-5', EUR, { signed: true }), filterCents('−0,01', EUR, { signed: true }), filterCents('-5', EUR)]).toEqual([-500, -1, undefined]);
  });
});

// hub#1196: every list says under an amount end it cannot read what the money field (`MoneyInput`) says for it, in its
// words: not an amount, negative, or «1.000» that reads two ways; nothing while the business's money is unknown.
describe('amountFilterErrors', () => {
  const EUR = { currency: 'EUR', decimals: 2 };
  const ENDS = ['total_from', 'total_to'] as const;
  /** How a list in `locale` says an end, in a business in euros unless `money` says another (`undefined`: unknown). */
  const say = (locale: 'en' | 'es', { money = EUR as typeof EUR | undefined, signed = undefined as readonly string[] | undefined } = {}) => {
    const i18n = createShellI18n({ locale, messages: { en, es } });
    const t = (key: string, named?: Record<string, unknown>) => (named ? i18n.global.t(key, named) : i18n.global.t(key));
    return { t, locale, money, signed };
  };
  /** What the money field says for `typed`, from its own catalogue. */
  const field = (messages: typeof moneyFieldEn, key: 'notAmount' | 'negative' | 'ambiguous', named: Record<string, string> = {}) =>
    Object.entries(named).reduce((text, [name, value]) => text.replace(`{${name}}`, value), messages.moneyInput[key]);

  it('says under each end what the money field says for it, in both languages; an empty end or an amount says nothing', () => {
    expect(amountFilterErrors({ total_from: 'doce', total_to: '1.000', other: 'x' }, ENDS, say('en'))).toEqual({
      total_from: field(moneyFieldEn, 'notAmount', { amount: '12.50' }),
      total_to: field(moneyFieldEn, 'ambiguous', { typed: '1.000', grouped: formatMoney(100000, 'en', EUR), decimal: formatMoney(100, 'en', EUR) }),
    });
    expect(amountFilterErrors({ total_from: '-5', total_to: ' 1.000 ' }, ENDS, say('es'))).toEqual({
      total_from: field(moneyFieldEs, 'negative'),
      total_to: field(moneyFieldEs, 'ambiguous', { typed: '1.000', grouped: formatMoney(100000, 'es', EUR), decimal: formatMoney(100, 'es', EUR) }),
    });
    expect(amountFilterErrors({ total_from: '1.000,50', total_to: '' }, ENDS, say('en'))).toEqual({});
  });

  it('«not an amount» gives its example in the business’s money, as the money field does: «12» in yen, «12,500» in dinars (ui#140)', () => {
    const typed = { total_from: 'doce', total_to: '' };
    expect(
      (['en', 'es'] as const).flatMap((locale) =>
        [EUR, { currency: 'JPY', decimals: 0 }, { currency: 'KWD', decimals: 3 }].map((money) => amountFilterErrors(typed, ENDS, say(locale, { money })).total_from),
      ),
    ).toEqual([
      field(moneyFieldEn, 'notAmount', { amount: '12.50' }),
      field(moneyFieldEn, 'notAmount', { amount: '12' }),
      field(moneyFieldEn, 'notAmount', { amount: '12.500' }),
      field(moneyFieldEs, 'notAmount', { amount: '12,50' }),
      field(moneyFieldEs, 'notAmount', { amount: '12' }),
      field(moneyFieldEs, 'notAmount', { amount: '12,500' }),
    ]);
    expect(field(moneyFieldEs, 'notAmount', { amount: '12' })).toBe('Esto no es un importe. Escribe una cifra, por ejemplo 12.');
  });

  it('a signed end (a difference) reads its minus; the same minus on another end cannot be negative', () => {
    expect(amountFilterErrors({ total_from: '-5', total_to: '-5' }, ENDS, say('en', { signed: ['total_from'] }))).toEqual({ total_to: field(moneyFieldEn, 'negative') });
  });

  it('judges nothing while the business’s money is unknown, as the money field does (hub#945)', () => {
    expect(amountFilterErrors({ total_from: '12,50 zł', total_to: 'doce' }, ENDS, { ...say('en'), money: undefined })).toEqual({});
  });
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

/** A window that waits for the money: what `useBusinessMoneyRead` says of it, and its «Retry». */
const Reader = {
  setup() {
    const read = useBusinessMoneyRead();
    return () =>
      h('div', [
        h('span', { 'data-testid': 'read' }, JSON.stringify({ money: read.money.value ?? null, error: read.error.value?.code ?? null })),
        h('button', { 'data-testid': 'retry', onClick: read.retry }),
      ]);
  },
};

describe('useBusinessMoneyRead (hub#938)', () => {
  it("is the money and the read's error, and «retry» asks the server again; the answer clears the error", async () => {
    const m = await mountBase(Reader);
    const call = await m.live();
    const said = () => JSON.parse(m.wrapper.find('[data-testid="read"]').text());
    expect(said()).toEqual({ money: null, error: null });
    call.push(errorFrame(subId(m.client, 'base.business.get'), 'base.hub_busy'));
    await flush();
    expect(said()).toEqual({ money: null, error: 'base.hub_busy' });
    const asked = m.net.streams.length;
    await m.wrapper.find('[data-testid="retry"]').trigger('click');
    await flush();
    expect(m.net.streams.length).toBe(asked + 1);
    await m.result(m.net.lastStream(), 'base.business.get', business(POLISH));
    expect(said()).toEqual({ money: { currency: 'PLN', decimals: 2 }, error: null });
  });

  it('shares the one subscription of the tab with useBusinessMoney', async () => {
    const Both = {
      setup() {
        useBusinessMoney();
        useBusinessMoneyRead();
        return () => h('div');
      },
    };
    const m = await mountBase(Both);
    await m.live();
    expect(m.client.stream.subscriptions('base.business.get')).toHaveLength(1);
  });
});

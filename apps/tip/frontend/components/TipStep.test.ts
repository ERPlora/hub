// The «Tip» row of Sales' charge sheet (TIP-F02): with tips on, «No tip», the payment method's three suggestions with
// the tip each comes to and «Other amount»; it says what it adds to the charge and, once the sale is charged, records
// the tip with that sale, once per attempt.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, flush, ionValue } from '../../../../base/frontend/__tests__/mount-in-shell';
import type { Added } from '../../../sale/frontend/lib/checkout/steps';
import { plain } from '../../../sale/frontend/lib/format';
import type { SaleOut } from '../../../sale/frontend/operations';
import { mountTip } from '../__tests__/mount-tip';
import type { SuggestionOut } from '../operations';
import TipStep from './TipStep.vue';

const OP = 'tip.suggestion.get';
const CARD = { id: 'm-card', display_name: 'Card', type: 'card' as const, requires_change: false };
const CASH = { id: 'm-cash', display_name: 'Cash', type: 'cash' as const, requires_change: true };

const ON: SuggestionOut = {
  enabled: true,
  allow_custom: true,
  preselected: 2,
  suggestions: [
    { percent: 3, amount: 30 },
    { percent: 5, amount: 50 },
    { percent: null, amount: 200 },
  ],
};

const SALE = {
  id: 's1',
  number: '20261125-0001',
  payments: [{ id: 'p1', position: 0, method_id: 'm-card', method_name: 'Card', method_type: 'card', amount: 1000, extra: 50 }],
} as unknown as SaleOut;

async function setup(read: SuggestionOut | null = ON, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTip(TipStep, { props: { total: 900, discount: 100, method: CARD, locked: false, ...props }, locale });
  await m.live();
  if (read) await m.result(OP, read);
  const added = () => m.wrapper.emitted<[Added]>('update:added')?.at(-1)?.[0];
  const choice = (testid: string) => m.find(testid).element as HTMLElement;
  const said = (testid: string) => plain(m.find(testid).text());
  const pressed = () =>
    m.wrapper.findAll('[aria-pressed="true"]').map((button) => button.attributes('data-testid'));
  const record = (sale: SaleOut = SALE) =>
    (m.wrapper.vm as unknown as { afterCharge: (s: SaleOut, k: string) => Promise<void> }).afterCharge(sale, 'sale-key');
  return { ...m, added, choice, said, pressed, record };
}

describe('TipStep: what it reads', () => {
  it('asks the suggestions of the method chosen on the check’s total before discounts', async () => {
    const s = await setup(null);
    expect(s.params(OP)).toEqual([{ method_id: 'm-card', total: 1000 }]);
  });

  it('while they load: says so and adds nothing', async () => {
    const s = await setup(null);
    expect(s.find('tip-step-loading').text()).toBe('Loading the tips…');
    expect(s.added()).toEqual({ amount: 0, label: 'Tip', issue: '' });
  });

  it('a read that fails says the server’s words with «Retry», which asks again', async () => {
    const s = await setup(null);
    s.net.lastStream().push(errorFrame(s.subId(OP), 'tip.boom'));
    await flush();
    expect(s.find('tip-step-error').text()).toContain('msg tip.boom');
    const streams = s.net.streams.length;
    await click(s.choice('tip-step-retry'));
    await s.reopen();
    expect(s.net.streams.length).toBe(streams + 1);
  });

  it('with tips off: paints nothing and adds nothing', async () => {
    const s = await setup({ ...ON, enabled: false, suggestions: [] });
    expect(s.find('tip-step').exists()).toBe(false);
    expect(s.added()).toEqual({ amount: 0, label: 'Tip', issue: '' });
  });
});

describe('TipStep: choosing the tip', () => {
  it('offers «No tip», each suggestion with the tip it comes to and «Other amount», opening on the one marked', async () => {
    const s = await setup();
    expect(s.find('tip-step-none').text()).toBe('No tip');
    expect(s.said('tip-step-suggestion-0')).toBe('3% · €0.30');
    expect(s.find('tip-step-suggestion-2').text()).toBe('€2.00');
    expect(s.find('tip-step-custom').text()).toBe('Other amount');
    expect(s.pressed()).toEqual(['tip-step-suggestion-1']);
    expect(s.added()).toEqual({ amount: 50, label: 'Tip', issue: '' });
  });

  it('a tap chooses: a suggestion adds its tip, «No tip» adds nothing', async () => {
    const s = await setup();
    await click(s.choice('tip-step-suggestion-2'));
    expect([s.pressed(), s.added()?.amount]).toEqual([['tip-step-suggestion-2'], 200]);
    await click(s.choice('tip-step-none'));
    expect([s.pressed(), s.added()?.amount]).toEqual([['tip-step-none'], 0]);
  });

  it('another amount is typed in the money field; one that does not read stops the charge with its words', async () => {
    const s = await setup();
    await click(s.choice('tip-step-custom'));
    expect(s.added()?.amount).toBe(0);
    await ionValue(s.find('tip-step-amount').element, '2,50', 'ionInput');
    expect(s.added()).toEqual({ amount: 250, label: 'Tip', issue: '' });
    await ionValue(s.find('tip-step-amount').element, 'abc', 'ionInput');
    expect(s.added()).toEqual({ amount: 0, label: 'Tip', issue: 'Write the tip as an amount.' });
  });

  it('without another amount allowed, only the suggestions and «No tip»', async () => {
    const s = await setup({ ...ON, allow_custom: false });
    expect(s.find('tip-step-custom').exists()).toBe(false);
  });

  it('another method keeps an amount chosen and its percentages follow the total', async () => {
    const s = await setup();
    await click(s.choice('tip-step-suggestion-2'));
    await s.wrapper.setProps({ method: CASH });
    await s.reopen();
    await s.result(OP, { ...ON, suggestions: [{ percent: 10, amount: 100 }, { percent: null, amount: 100 }, { percent: null, amount: 500 }] }, { method_id: 'm-cash' });
    expect([s.pressed(), s.added()?.amount]).toEqual([['tip-step-custom'], 200]);
  });

  it('the same method’s suggestions read again keep what was chosen, with the tip it comes to now', async () => {
    const s = await setup();
    await click(s.choice('tip-step-suggestion-0'));
    await s.result(OP, { ...ON, suggestions: [{ percent: 3, amount: 60 }, { percent: 5, amount: 100 }, { percent: null, amount: 200 }] });
    expect([s.pressed(), s.added()?.amount]).toEqual([['tip-step-suggestion-0'], 60]);
  });

  it('tips turned off with the sheet open: the row goes and what was typed is not added', async () => {
    const s = await setup();
    await click(s.choice('tip-step-custom'));
    await ionValue(s.find('tip-step-amount').element, '2,50', 'ionInput');
    expect(s.added()?.amount).toBe(250);
    await s.result(OP, { ...ON, enabled: false, suggestions: [] });
    expect(s.find('tip-step').exists()).toBe(false);
    expect(s.added()).toEqual({ amount: 0, label: 'Tip', issue: '' });
  });

  it('once the sale is charged nothing changes', async () => {
    const s = await setup(ON, { locked: true });
    const disabled = (testid: string) => (s.choice(testid) as HTMLElement & { disabled?: boolean }).disabled;
    expect(['tip-step-none', 'tip-step-suggestion-0', 'tip-step-custom'].map(disabled)).toEqual([true, true, true]);
  });

  it('in Spanish', async () => {
    const s = await setup(ON, {}, 'es');
    expect(s.find('tip-step-none').text()).toBe('Sin propina');
    expect(s.said('tip-step-suggestion-0')).toBe('3 % · 0,30 €');
    expect(s.added()?.label).toBe('Propina');
  });
});

describe('TipStep: once the sale is charged', () => {
  it('records the tip with its sale, the payment that charged it and the attempt key of that payment', async () => {
    const s = await setup();
    s.answer(201, { id: 't1', sale_id: 's1', amount: 50, status: 'active' });
    await s.record();
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([
      {
        method: 'POST',
        path: '/api/tip/tips',
        query: {},
        body: { sale_id: 's1', method_id: 'm-card', amount: 50, attempt_key: 'sale-key:0' },
      },
    ]);
  });

  it('with no tip chosen records nothing', async () => {
    const s = await setup({ ...ON, preselected: 0 });
    await s.record();
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([]);
  });

  it('a tip that is not saved says so with the server’s words', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'tip.cash_register_closed', message: 'The cash register is closed.' } });
    await expect(s.record()).rejects.toThrow('The sale is charged, but the tip has not been saved. The cash register is closed.');
  });

  it('an answer that is lost says only that it was not saved: what a server that fails says is not for the till', async () => {
    const s = await setup();
    s.answer(503, { error: { code: 'unavailable', message: 'Upstream is restarting.' } });
    await expect(s.record()).rejects.toThrow(/^The sale is charged, but the tip has not been saved\.$/);
  });
});

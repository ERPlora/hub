// The charge sheet with a step another app adds to it (SALE-F39; the tip of Tips is one): the step sits between the
// amount and the tenders, what it adds is charged with the sale on its one payment but apart from it, and the sheet
// hands the sale to the till once the step has recorded its part.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { shallowRef } from 'vue';

import { appComponent } from '../../../../../base/frontend/lib/app-components';
import { click, flush } from '../../__tests__/mount-sale';
import { preview, SALE, setup as setupPanel } from './__tests__/checkout-panel';
import { fakeStep, type Recorder } from './__tests__/fake-step';

// The real loader, spied on: each test says which component a step's name brings.
vi.mock('../../../../../base/frontend/lib/app-components', { spy: true });

const STEPS_OP = 'sale.checkout.steps';
const TIP = { key: 'tip.tip', app: 'tip', component: 'TipStep' };

/** What the step adds now, and its record of a charged sale. */
const adding = shallowRef({ amount: 50, label: 'Tip', issue: '' });
const record = vi.fn<Recorder>(() => Promise.resolve());

const Step = fakeStep('tip-row', () => adding.value, record);

afterEach(() => {
  adding.value = { amount: 50, label: 'Tip', issue: '' };
  record.mockReset().mockResolvedValue(undefined);
});

async function setup(options: Parameters<typeof setupPanel>[0] = {}) {
  vi.mocked(appComponent).mockImplementation((_app, name) => (name === 'TipStep' ? () => Promise.resolve({ default: Step }) : undefined));
  const s = await setupPanel(options);
  await s.push(STEPS_OP, { steps: [TIP] });
  await vi.waitFor(() => expect(s.find('tip-row').exists()).toBe(true));
  return s;
}

/** The sheet with the step, charged by card: the server records the sale. */
async function chargedByCard() {
  const s = await setup();
  s.replies({ '/api/sale/sales': [Response.json(SALE)] });
  await click(s.find('sale-checkout-method-m-card').element);
  await click(s.confirm());
  return s;
}

describe('CheckoutPanel: a step of another app (SALE-F39)', () => {
  it('sits between the amount and the tenders with the charge’s total, its discounts and the method chosen', async () => {
    const s = await setup({ preview: preview({ discount_amount: 300 }) });
    expect(s.params(STEPS_OP)).toEqual([{}]);
    expect(s.find('tip-row').text()).toBe('4250/300/m-cash/false');
    await click(s.find('sale-checkout-method-m-card').element);
    expect(s.find('tip-row').text()).toBe('4250/300/m-card/false');
  });

  it('what it adds is said under the amount and charged on the card with the sale, apart from it and named', async () => {
    const s = await setup();
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    expect(s.text('sale-checkout-total')).toBe('€42.50');
    expect(s.text('sale-checkout-added')).toBe('+ €0.50 tip');
    await click(s.find('sale-checkout-method-m-card').element);
    expect(s.text('sale-checkout-hint')).toBe('Charge €43.00 on the card terminal, then confirm.');
    expect(s.label()).toBe('Charge €43.00 by card');
    await click(s.confirm());
    expect(s.body().payments).toEqual([{ method_id: 'm-card', extra: 50, extra_label: 'Tip' }]);
  });

  it('in cash, what is handed over covers the sale and what is added, and the change takes both off', async () => {
    const s = await setup();
    await s.type('4', '2', 'dot', '5', '0');
    expect(s.label()).toBe('The amount tendered does not cover the total');
    await s.type('clear', '5', '0');
    expect(s.text('sale-checkout-change')).toBe('Change €7.00');
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.confirm());
    expect(s.body().payments).toEqual([{ method_id: 'm-cash', tendered: 5000, extra: 50, extra_label: 'Tip' }]);
  });

  it('nothing added: the sheet as always', async () => {
    adding.value = { amount: 0, label: 'Tip', issue: '' };
    const s = await setup();
    expect(s.find('sale-checkout-added').exists()).toBe(false);
    await click(s.find('sale-checkout-method-m-card').element);
    expect(s.label()).toBe('Charge €42.50 by card');
  });

  it('a step that cannot be charged as it stands stops the charge with its words', async () => {
    adding.value = { amount: 0, label: 'Tip', issue: 'Write the tip as an amount.' };
    const s = await setup();
    await click(s.find('sale-checkout-method-m-card').element);
    expect(s.label()).toBe('Write the tip as an amount.');
    await click(s.confirm());
    expect(s.charges()).toEqual([]);
  });

  it('splitting the payment takes the step away: each leg charges the sale only', async () => {
    const s = await setup();
    await click(s.find('sale-checkout-split').element);
    expect(s.find('tip-row').exists()).toBe(false);
    expect(s.find('sale-checkout-added').exists()).toBe(false);
    expect(s.text('sale-checkout-remaining')).toBe('Remaining €42.50');
  });

  it('once charged the step records its part with the sale and this attempt’s key, and then the till gets the sale', async () => {
    let recorded!: () => void;
    record.mockImplementation(() => new Promise<void>((resolve) => (recorded = resolve)));
    const s = await chargedByCard();
    expect(record).toHaveBeenCalledWith(SALE, s.body().idempotency_key);
    expect(s.find('tip-row').text()).toBe('4250/0/m-card/true');
    expect(s.wrapper.emitted('charged')).toBeUndefined();
    expect(s.wrapper.emitted('busy')?.at(-1)).toEqual([true]);
    recorded();
    await flush();
    expect(s.wrapper.emitted('charged')).toEqual([[SALE, []]]);
    expect(s.wrapper.emitted('busy')?.at(-1)).toEqual([false]);
  });

  it('a step that cannot record keeps the sheet with its words and nothing to charge; «Close» hands the sale to the till', async () => {
    record.mockRejectedValue(new Error('The sale is charged, but the tip has not been saved.'));
    const s = await chargedByCard();
    expect(s.find('sale-checkout-steps-failed').text()).toContain('The sale is charged, but the tip has not been saved.');
    expect(s.find('sale-checkout-confirm').exists()).toBe(false);
    expect(s.wrapper.emitted('charged')).toBeUndefined();
    await click(s.find('sale-checkout-steps-close').element);
    expect(s.wrapper.emitted('charged')).toEqual([[SALE, []]]);
  });

  it('in Spanish', async () => {
    adding.value = { amount: 50, label: 'Propina', issue: '' };
    const s = await setup({ locale: 'es' });
    expect(s.text('sale-checkout-added')).toBe('+ 0,50 € de propina');
  });
});

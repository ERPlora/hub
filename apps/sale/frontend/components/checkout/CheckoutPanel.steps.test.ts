// The charge sheet with a step another app adds to it (SALE-F39; the tip of Tips is one): the step sits between the
// amount and the tenders, what it adds is charged with the sale on its one payment but apart from it, and the sheet
// hands the sale to the till once the step has recorded its part.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, shallowRef, watch } from 'vue';

import { appComponent } from '../../../../../base/frontend/lib/app-components';
import { click, flush } from '../../__tests__/mount-sale';
import type { SaleOut } from '../../operations';
import { SALE, setup as setupPanel } from './__tests__/checkout-panel';

vi.mock('../../../../../base/frontend/lib/app-components', async (actual) => ({
  ...(await actual<typeof import('../../../../../base/frontend/lib/app-components')>()),
  appComponent: vi.fn(),
}));

const STEPS_OP = 'sale.checkout.steps';
const TIP = { key: 'tip.tip', app: 'tip', component: 'TipStep' };

/** What the step adds now, and its record of a charged sale. */
const adding = shallowRef({ amount: 50, label: 'Tip', issue: '' });
const record = vi.fn<(sale: SaleOut, key: string) => Promise<void>>(() => Promise.resolve());

const Step = defineComponent({
  props: {
    total: { type: Number, required: true },
    discount: { type: Number, required: true },
    method: { type: Object, required: true },
    locked: { type: Boolean, required: true },
  },
  emits: ['update:added'],
  setup(props, { emit, expose }) {
    watch(adding, (now) => emit('update:added', now), { immediate: true });
    expose({ afterCharge: record });
    return () =>
      h('p', { 'data-testid': 'tip-row' }, `${props.total}/${props.discount}/${(props.method as { id: string }).id}/${props.locked}`);
  },
});

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

describe('CheckoutPanel: a step of another app (SALE-F39)', () => {
  it('sits between the amount and the tenders with the charge’s total, its discounts and the method chosen', async () => {
    const s = await setup({ preview: undefined });
    expect(s.params(STEPS_OP)).toEqual([{}]);
    expect(s.find('tip-row').text()).toBe('4250/0/m-cash/false');
    await click(s.find('sale-checkout-method-m-card').element);
    expect(s.find('tip-row').text()).toBe('4250/0/m-card/false');
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
    const s = await setup();
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.confirm());
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
    const s = await setup();
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.confirm());
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

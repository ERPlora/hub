// The steps the apps on add to the charge (SALE-F39), mounted between the amount and the tenders by their app and
// their component's name, without Sales knowing them: what they add is added up for the charge, and once the sale is
// charged each records its part; one that cannot is said with «Retry» and «Close».
import { afterEach, describe, expect, it, vi } from 'vitest';

import { appComponent, type ComponentLoader } from '../../../../../base/frontend/lib/app-components';
import { click, errorFrame, flush, mountSale } from '../../__tests__/mount-sale';
import type { Added } from '../../lib/checkout/steps';
import type { SaleOut } from '../../operations';
import CheckoutSteps from './CheckoutSteps.vue';
import { fakeStep, type Recorder } from './__tests__/fake-step';

// The real loader, spied on: each test says which component a step's name brings.
vi.mock('../../../../../base/frontend/lib/app-components', { spy: true });

const OP = 'sale.checkout.steps';
const CARD = { id: 'm-card', display_name: 'Card', type: 'card' as const, requires_change: false };
const SALE = { id: 's1', number: '20261125-0001' } as SaleOut;
const TIP = { key: 'tip.tip', app: 'tip', component: 'TipStep' };
const ROUND = { key: 'round.round', app: 'round', component: 'RoundStep' };

const recordTip = vi.fn<Recorder>(() => Promise.resolve());
const recordRound = vi.fn<Recorder>(() => Promise.resolve());
const LOADERS: Record<string, ComponentLoader> = {
  TipStep: () => Promise.resolve({ default: fakeStep('step-Tip', () => ({ amount: 50, label: 'Tip', issue: '' }), recordTip) }),
  RoundStep: () => Promise.resolve({ default: fakeStep('step-Round', () => ({ amount: 30, label: 'Round', issue: '' }), recordRound) }),
  Broken: () => Promise.reject(new Error('the chunk did not arrive')),
};

afterEach(() => {
  vi.mocked(appComponent).mockReset();
  recordTip.mockReset().mockResolvedValue(undefined);
  recordRound.mockReset().mockResolvedValue(undefined);
});

async function setup(steps: (typeof TIP)[] | null = [TIP]) {
  vi.mocked(appComponent).mockImplementation((_app, name) => LOADERS[name]);
  const m = await mountSale(CheckoutSteps, { props: { total: 900, discount: 100, method: CARD, locked: false } });
  await m.live();
  if (steps) await m.result(OP, { steps });
  await vi.waitFor(() => expect(m.wrapper.findAll('[data-testid^="step-"]').length).toBe(steps?.filter((s) => s.component !== 'Broken').length ?? 0));
  const added = () => m.wrapper.emitted<[Added]>('update:added')?.at(-1)?.[0];
  const charged = async () => {
    (m.wrapper.vm as unknown as { afterCharge: (sale: SaleOut, key: string) => void }).afterCharge(SALE, 'sale-key');
    await flush();
  };
  return { ...m, added, charged };
}

describe('CheckoutSteps: the steps of the apps on', () => {
  it('mounts each by its app and its name, with the charge’s total, its discounts and whether it is charged', async () => {
    const s = await setup([TIP]);
    expect(appComponent).toHaveBeenCalledWith('tip', 'TipStep');
    expect(s.find('step-Tip').text()).toBe('900/100/m-card/false');
  });

  it('adds up what they add', async () => {
    const s = await setup([TIP, ROUND]);
    expect(s.added()).toEqual({ amount: 80, label: 'Tip, Round', issue: '' });
  });

  it('none while their list loads, and nothing added', async () => {
    const s = await setup(null);
    expect(s.find('sale-checkout-steps').exists()).toBe(false);
    expect(s.added()).toEqual({ amount: 0, label: '', issue: '' });
  });

  it('a step whose code does not arrive is left out and logged, and the others stay', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const s = await setup([{ key: 'x.broken', app: 'x', component: 'Broken' }, TIP]);
    expect(s.added()).toEqual({ amount: 50, label: 'Tip', issue: '' });
    await vi.waitFor(() => expect(warn).toHaveBeenCalledWith(expect.stringContaining('the step x.broken of the charge could not load'), expect.any(Error)));
  });

  it('a list that cannot be read says the server’s words with «Retry»', async () => {
    const s = await setup(null);
    s.net.lastStream().push(errorFrame(s.subId(OP), 'sale.boom'));
    await flush();
    expect(s.find('sale-checkout-steps-error').text()).toContain('msg sale.boom');
    const streams = s.net.streams.length;
    await click(s.find('sale-checkout-steps-reload').element);
    await s.reopen();
    expect(s.net.streams.length).toBe(streams + 1);
  });
});

describe('CheckoutSteps: once the sale is charged', () => {
  it('each step records its part with the sale and the attempt key, and then it is done', async () => {
    const s = await setup([TIP, ROUND]);
    await s.charged();
    expect(recordTip).toHaveBeenCalledWith(SALE, 'sale-key');
    expect(recordRound).toHaveBeenCalledWith(SALE, 'sale-key');
    expect(s.wrapper.emitted('done')).toEqual([[]]);
  });

  it('with no step it is done at once', async () => {
    const s = await setup([]);
    await s.charged();
    expect(s.wrapper.emitted('done')).toEqual([[]]);
  });

  it('a step that cannot record says its words; «Retry» asks only that one again and it is done once it records', async () => {
    recordTip.mockRejectedValueOnce(new Error('The sale is charged, but the tip has not been saved.'));
    const s = await setup([TIP, ROUND]);
    await s.charged();
    expect(s.wrapper.emitted('done')).toBeUndefined();
    expect(s.find('sale-checkout-steps-failed').text()).toContain('The sale is charged, but the tip has not been saved.');
    await click(s.find('sale-checkout-steps-retry').element);
    expect([recordTip.mock.calls.length, recordRound.mock.calls.length]).toEqual([2, 1]);
    expect(s.find('sale-checkout-steps-failed').exists()).toBe(false);
    expect(s.wrapper.emitted('done')).toEqual([[]]);
  });

  it('«Close» leaves it as it is and is done: the sale is charged', async () => {
    recordTip.mockRejectedValue(new Error('The sale is charged, but the tip has not been saved.'));
    const s = await setup([TIP]);
    await s.charged();
    await click(s.find('sale-checkout-steps-close').element);
    expect(s.wrapper.emitted('done')).toEqual([[]]);
  });
});

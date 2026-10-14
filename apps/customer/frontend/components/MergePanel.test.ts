// «Merge with…» on the card (CUSTOMER-F13), the product's panel: the open card is the one that
// STAYS; pick the duplicate (never itself), read what will happen to it, «Merge». Then «{name} was
// merged into this customer.». A refusal stays in the panel; «Pick another» and «Cancel» go back.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { customerRow, pageOf } from '../__tests__/fixtures';
import { flush, json, type MountOptions, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import CustomerPicker from './CustomerPicker.vue';
import MergePanel from './MergePanel.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const DUPLICATE = customerRow('c2', 'Ana G.');

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(MergePanel, { props: { customer: { id: 'c1', name: 'Ana García' } }, ...options });
  const call = await m.live();
  await m.result(call, 'customer.customer.list', pageOf([customerRow('c1', 'Ana García'), DUPLICATE]));
  const pick = async () => {
    m.wrapper.findComponent(CustomerPicker).vm.$emit('pick', DUPLICATE);
    await flush();
  };
  const click = async (id: string) => {
    await m.wrapper.get(`[data-testid="${id}"]`).trigger('click');
    await flush();
  };
  return { ...m, call, pick, click };
}

describe('MergePanel', () => {
  it('asks for the duplicate of the open card, which never offers itself', async () => {
    const s = await setup();
    expect(s.wrapper.get('h3').text()).toBe('Merge a duplicate customer');
    expect(s.wrapper.text()).toContain('Pick the duplicate of Ana García. Ana García stays; the one you pick is merged into it.');
    const picker = s.wrapper.findComponent(CustomerPicker);
    expect(picker.props('exclude')).toEqual(['c1']);
    expect(picker.props('emptyMessage')).toBe('No other customer matches.');
    expect(picker.props('placeholder')).toBe('Search the duplicate');
  });

  it('a pick shows what will happen, and «Merge» merges it into the open card', async () => {
    const s = await setup();
    await s.pick();
    expect(s.wrapper.get('[data-testid="customer-merge-confirm"]').text()).toContain(
      'Ana G. will be merged into Ana García: its appointments, sales, bookings, conversations, prepaid packages, notes and consents move to Ana García',
    );
    s.net.onApi(() => json({ id: 'c1', name: 'Ana García' }));
    await s.click('customer-merge-submit');
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/customers/merge', body: { id: 'c1', absorbed_id: 'c2' } });
    expect(toastSuccess).toHaveBeenCalledWith('Ana G. was merged into this customer.');
    expect(s.wrapper.emitted('done')).toHaveLength(1);
  });

  it('«Pick another» goes back to the search; «Cancel» closes', async () => {
    const s = await setup();
    await s.pick();
    await s.click('customer-merge-change');
    expect(s.wrapper.findComponent(CustomerPicker).exists()).toBe(true);
    await s.click('customer-merge-cancel');
    expect(s.wrapper.emitted('done')).toHaveLength(1);
    expect(s.net.api).toHaveLength(0);
  });

  it('a refusal (one of them is gone) stays in the panel', async () => {
    const s = await setup();
    await s.pick();
    s.net.onApi(() => refusal(404, 'customer.customer_unavailable', 'This customer is no longer available.'));
    await s.click('customer-merge-submit');
    expect(s.wrapper.get('[data-testid="customer-merge-error"]').text()).toContain('This customer is no longer available.');
    expect(s.wrapper.emitted('done')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.get('h3').text()).toBe('Fusionar una ficha duplicada');
    await s.pick();
    expect(s.wrapper.get('[data-testid="customer-merge-submit"]').text()).toBe('Fusionar');
  });
});

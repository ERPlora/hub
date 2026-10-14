// «Groups» and «Tags» on the card (CUSTOMER-F06): a checkbox per group (or tag) of the business, the
// card's own ticked; «Save groups» sends the WHOLE selection, which replaces the previous one. A group
// that is no longer active is still shown on the cards that have it. Who cannot manage cards only sees.
import { toastSuccess } from '@erplora/ui/shell';
import { IonCheckbox } from '@ionic/vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, json, type MountOptions, mountCustomer, refusal, sent, subId } from '../__tests__/mount-customer';
import { pageOf } from '../__tests__/fixtures';
import MembershipEditor from './MembershipEditor.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const group = (id: string, name: string, is_active = true) => ({ id, name, description: '', color: 'primary', sort_order: 0, is_active, customer_count: 1 });
const GROUPS = pageOf([group('g1', 'VIP'), group('g2', 'Staff'), group('g3', 'Old', false), group('g4', 'Retired', false)]);

async function setup(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountCustomer(MembershipEditor, {
    props: { kind: 'groups', customerId: 'c1', selected: ['g1', 'g3'], editable: true, ...props },
    ...options,
  });
  const call = await m.live();
  const boxes = () =>
    m.wrapper.findAllComponents(IonCheckbox).map((b) => [b.attributes('data-testid'), b.text(), b.props('checked'), b.props('disabled')]);
  const save = () => m.wrapper.find('[data-testid="customer-groups-save"]');
  return { ...m, call, boxes, save };
}

describe('MembershipEditor', () => {
  it('lists the active groups and the inactive ones the card has, its own ticked', async () => {
    const s = await setup();
    expect(s.params('customer.group.list')).toEqual([{ limit: 100, sort: 'name' }]);
    expect(s.params('customer.tag.list'), 'only the list it edits').toEqual([]);
    await s.result(s.call, 'customer.group.list', GROUPS);
    expect(s.wrapper.get('h3').text()).toBe('Groups');
    expect(s.boxes()).toEqual([
      ['customer-groups-item-g1', 'VIP', true, false],
      ['customer-groups-item-g2', 'Staff', false, false],
      ['customer-groups-item-g3', 'Old (not active)', true, false],
    ]);
  });

  it('«Save groups» sends the whole selection, by id, and says «Groups assigned»', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.net.onApi(() => json({ id: 'c1' }));
    s.wrapper.findAllComponents(IonCheckbox)[1].vm.$emit('ionChange', { detail: { checked: true } });
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: false } });
    await flush();
    expect(s.save().text()).toBe('Save groups');
    await s.save().trigger('click');
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/customers/set_groups', body: { id: 'c1', group_ids: ['g3', 'g2'] } });
    expect(toastSuccess).toHaveBeenCalledWith('Groups assigned');
  });

  it('a group deleted meanwhile is told, and nothing is saved', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.net.onApi(() => refusal(422, 'customer.group_unavailable', 'That group no longer exists.', { group_ids: 'That group no longer exists.' }));
    await s.save().trigger('click');
    await flush();
    expect(s.wrapper.get('[data-testid="customer-groups-error"]').text()).toContain('That group no longer exists.');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('follows the card: a new selection from the server ticks the boxes (an inactive group it left goes)', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    await s.wrapper.setProps({ selected: ['g2'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', false],
      ['Staff', true],
    ]);
  });

  it('with more than 100 groups offers a search on the server; what was ticked stays ticked while searching', async () => {
    const s = await setup();
    expect(s.wrapper.find('[data-testid="customer-groups-search"]').exists()).toBe(false);
    await s.result(s.call, 'customer.group.list', { ...GROUPS, total: 140 });
    const bar = s.wrapper.get('[data-testid="customer-groups-search"]').element as HTMLElement & { value?: string };
    bar.value = 'st';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'st' } }));
    await flush();
    expect(s.params('customer.group.list')).toEqual([{ limit: 100, sort: 'name', search: 'st' }]);
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    await flush();
    expect((sent(s.net.api[0]).body as { group_ids: string[] }).group_ids).toEqual(['g1', 'g3']);
  });

  it('says «Loading…» until the groups arrive', async () => {
    const s = await setup();
    expect(s.wrapper.get('[data-testid="customer-groups-loading"]').text()).toBe('Loading…');
    await s.result(s.call, 'customer.group.list', GROUPS);
    expect(s.wrapper.find('[data-testid="customer-groups-loading"]').exists()).toBe(false);
  });

  it('with no groups says «No groups.»', async () => {
    const s = await setup({ selected: [] });
    await s.result(s.call, 'customer.group.list', pageOf([]));
    expect(s.wrapper.get('[data-testid="customer-groups-empty"]').text()).toBe('No groups.');
    expect(s.save().exists()).toBe(false);
  });

  it('who cannot manage cards sees the boxes off and no «Save»', async () => {
    const s = await setup({ editable: false });
    await s.result(s.call, 'customer.group.list', GROUPS);
    expect(s.boxes().every((b) => b[3] === true)).toBe(true);
    expect(s.save().exists()).toBe(false);
  });

  it('the tags are the same, with their own texts and query', async () => {
    const s = await setup({ kind: 'tags', selected: ['t1'] });
    await s.result(s.call, 'customer.tag.list', pageOf([{ id: 't1', name: 'Loyal', color: 'primary', is_active: true, customer_count: 1 }]));
    expect(s.wrapper.get('h3').text()).toBe('Tags');
    expect(s.wrapper.get('[data-testid="customer-tags-save"]').text()).toBe('Save tags');
  });

  it('a failed load says so', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'customer.group.list'), 'boom'));
    await flush();
    expect(s.wrapper.get('[data-testid="customer-groups-error"]').text()).toContain('msg boom');
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, { locale: 'es' });
    await s.result(s.call, 'customer.group.list', GROUPS);
    expect(s.wrapper.get('h3').text()).toBe('Grupos');
    expect(s.save().text()).toBe('Guardar grupos');
    expect(s.boxes()[2][1]).toBe('Old (no activo)');
  });
});

// «Groups» and «Tags» on the card (CUSTOMER-F06): a checkbox per group (or tag) of the business, the
// card's own ticked; «Save groups» sends the WHOLE selection, which replaces the previous one. A group
// that is no longer active is still shown on the cards that have it. Who cannot manage cards only sees.
import { toastSuccess } from '@erplora/ui/shell';
import { IonCheckbox } from '@ionic/vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, json, type MountOptions, mountCustomer, refusal, sent, subId } from '../__tests__/mount-customer';
import { pageOf } from '../__tests__/fixtures';
import { namesGiven } from '../__tests__/searchbar-name';
import MembershipEditor from './MembershipEditor.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  syncSearchbarInputName: (await import('../__tests__/searchbar-name')).recordSearchbarName,
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const group = (id: string, name: string, is_active = true) => ({ id, name, description: '', color: 'primary', sort_order: 0, is_active, customer_count: 1 });
const GROUPS = pageOf([group('g1', 'VIP'), group('g2', 'Staff'), group('g3', 'Old', false), group('g4', 'Retired', false)]);
/** The refusal of a save with groups deleted meanwhile: it names them (`unavailable_ids`). */
const groupGone = (ids: string[]) =>
  json({ error: { code: 'customer.group_unavailable', message: 'That group no longer exists.', fields: { groups: 'That group no longer exists.' }, unavailable_ids: ids } }, 422);
/** `n` more active groups, for a business whose list needs the search. */
const OTHER_GROUPS = (n: number) => Array.from({ length: n }, (_, i) => group(`gx${i}`, `Group ${String(i).padStart(2, '0')}`));

async function setup(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountCustomer(MembershipEditor, {
    props: { kind: 'groups', customerId: 'c1', selected: ['g1', 'g3'], editable: true, ...props },
    ...options,
  });
  const call = await m.live();
  const boxes = () =>
    m.wrapper.findAllComponents(IonCheckbox).map((b) => [b.attributes('data-testid'), b.text(), b.props('checked'), b.props('disabled')]);
  const save = () => m.wrapper.find('[data-testid="customer-groups-save"]');
  /** Types in the search box; the stream reopens with the new query: its call. */
  async function search(text: string, kind = 'groups') {
    const bar = m.wrapper.get(`[data-testid="customer-${kind}-search"]`).element as HTMLElement & { value?: string };
    bar.value = text;
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: text } }));
    await flush();
    return m.live();
  }
  return { ...m, call, boxes, save, search };
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

  // The card's live result arrives again whenever the card changes (its other list saved, a note, someone
  // else): it must not untick what the user ticked and has not saved yet (hub#114: «Save tags» sent []
  // right after «Save groups», and the card lost the tag).
  it('a live result of the card between ticking and «Save groups» keeps the tick, and saving sends it', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[1].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    await s.wrapper.setProps({ selected: ['g1', 'g3'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', true],
      ['Staff', true],
      ['Old (not active)', true],
    ]);
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/customers/set_groups', body: { id: 'c1', group_ids: ['g1', 'g3', 'g2'] } });
  });

  it('someone else\'s change to the card does not undo an unsaved untick, and what they added shows and is kept', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: false } });
    await flush();
    await s.wrapper.setProps({ selected: ['g1', 'g2', 'g3'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', false],
      ['Staff', true],
      ['Old (not active)', true],
    ]);
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    await flush();
    expect((sent(s.net.api[0]).body as { group_ids: string[] }).group_ids).toEqual(['g2', 'g3']);
  });

  it('once saved it follows the card again', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[1].vm.$emit('ionChange', { detail: { checked: true } });
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    await flush();
    await s.wrapper.setProps({ selected: ['g1', 'g3', 'g2'] });
    await s.wrapper.setProps({ selected: ['g2'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', false],
      ['Staff', true],
    ]);
  });

  it('a tick made while «Save groups» is on its way is still unsaved: the card\'s result keeps it', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    const boxes = () => s.wrapper.findAllComponents(IonCheckbox);
    boxes()[1].vm.$emit('ionChange', { detail: { checked: true } });
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    boxes()[0].vm.$emit('ionChange', { detail: { checked: false } });
    await flush();
    expect((sent(s.net.api[0]).body as { group_ids: string[] }).group_ids).toEqual(['g1', 'g3', 'g2']);
    await s.wrapper.setProps({ selected: ['g1', 'g3', 'g2'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', false],
      ['Staff', true],
      ['Old (not active)', true],
    ]);
  });

  it('a box unticked right after saving, before the card\'s result arrives, stays unticked', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    const staff = () => s.wrapper.findAllComponents(IonCheckbox)[1];
    staff().vm.$emit('ionChange', { detail: { checked: true } });
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    await flush();
    staff().vm.$emit('ionChange', { detail: { checked: false } });
    await flush();
    await s.wrapper.setProps({ selected: ['g1', 'g3', 'g2'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', true],
      ['Staff', false],
      ['Old (not active)', true],
    ]);
  });

  // What is saved is what is seen: a live result of the card only keeps what the user ticked or
  // unticked; what someone else deleted or took off (and the user did not touch) leaves the selection.
  it('a saved group someone else deletes while a tick is unsaved leaves the selection: saving sends what is seen', async () => {
    const s = await setup({ selected: ['g1'] });
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[1].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    await s.result(s.call, 'customer.group.list', pageOf([group('g2', 'Staff'), group('g3', 'Old', false), group('g4', 'Retired', false)]));
    await s.wrapper.setProps({ selected: [] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([['Staff', true]]);
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    await flush();
    expect((sent(s.net.api[0]).body as { group_ids: string[] }).group_ids).toEqual(['g2']);
  });

  it('a ticked group someone else deletes is not sent: saving works, and again after it', async () => {
    const s = await setup({ selected: [] });
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    await s.result(s.call, 'customer.group.list', pageOf([group('g2', 'Staff'), group('g3', 'Old', false)]));
    await s.wrapper.setProps({ selected: [] });
    s.net.onApi((r) =>
      (sent(r).body as { group_ids: string[] }).group_ids.includes('g1')
        ? refusal(422, 'customer.group_unavailable', 'That group no longer exists.', { group_ids: 'That group no longer exists.' })
        : json({ id: 'c1' }),
    );
    await s.save().trigger('click');
    await flush();
    await s.save().trigger('click');
    await flush();
    expect(s.net.api.map((r) => (sent(r).body as { group_ids: string[] }).group_ids)).toEqual([[], []]);
    expect(s.wrapper.find('[data-testid="customer-groups-error"]').exists()).toBe(false);
  });

  // A deletion is only taken off the selection when the server says so: its refusal names the ids that
  // are gone. A list the user sees only part of (a search, more than 100) proves nothing.
  it('with a search on, after «That group no longer exists.» only the group it names leaves; the ticked ones the search hides stay', async () => {
    const s = await setup({ selected: [] });
    await s.result(s.call, 'customer.group.list', pageOf([group('g1', 'VIP'), group('g5', 'Gold'), ...OTHER_GROUPS(98)], 101));
    let call = await s.search('VIP');
    await s.result(call, 'customer.group.list', pageOf([group('g1', 'VIP')]));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    call = await s.search('Gold');
    await s.result(call, 'customer.group.list', pageOf([group('g5', 'Gold')]));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    // Someone deletes Gold.
    await s.result(call, 'customer.group.list', pageOf([]), 2);
    s.net.onApi((r) => ((sent(r).body as { group_ids: string[] }).group_ids.includes('g5') ? groupGone(['g5']) : json({ id: 'c1' })));
    await s.save().trigger('click');
    await flush();
    expect(s.wrapper.get('[data-testid="customer-groups-error"]').text()).toContain('That group no longer exists.');
    expect(s.params('customer.group.list')).toEqual([{ limit: 100, sort: 'name', search: 'Gold' }]);
    await s.save().trigger('click');
    await flush();
    expect(s.net.api.map((r) => (sent(r).body as { group_ids: string[] }).group_ids)).toEqual([['g1', 'g5'], ['g1']]);
    expect(toastSuccess).toHaveBeenCalledWith('Groups assigned');
  });

  it('with more than 100 groups, after the refusal the next save sends the ticked ones that exist and not the deleted one', async () => {
    const s = await setup({ selected: [] });
    await s.result(s.call, 'customer.group.list', pageOf([group('g1', 'VIP'), ...OTHER_GROUPS(99)], 140));
    let call = await s.search('Gold');
    await s.result(call, 'customer.group.list', pageOf([group('g5', 'Gold')]));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    call = await s.search('');
    await s.result(call, 'customer.group.list', pageOf([group('g1', 'VIP'), ...OTHER_GROUPS(99)], 139));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    s.net.onApi((r) => ((sent(r).body as { group_ids: string[] }).group_ids.includes('g5') ? groupGone(['g5']) : json({ id: 'c1' })));
    await s.save().trigger('click');
    await flush();
    await s.save().trigger('click');
    await flush();
    expect(s.net.api.map((r) => (sent(r).body as { group_ids: string[] }).group_ids)).toEqual([['g5', 'g1'], ['g1']]);
    expect(toastSuccess).toHaveBeenCalledWith('Groups assigned');
  });

  it('a refusal that names no group takes nothing off the selection', async () => {
    const s = await setup({ selected: [] });
    await s.result(s.call, 'customer.group.list', pageOf([group('g1', 'VIP'), ...OTHER_GROUPS(99)], 140));
    let call = await s.search('Gold');
    await s.result(call, 'customer.group.list', pageOf([group('g5', 'Gold')]));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    call = await s.search('VIP');
    await s.result(call, 'customer.group.list', pageOf([group('g1', 'VIP')]));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    s.net.onApi(() => refusal(422, 'customer.group_unavailable', 'That group no longer exists.', { groups: 'That group no longer exists.' }));
    await s.save().trigger('click');
    await flush();
    await s.save().trigger('click');
    await flush();
    expect(s.net.api.map((r) => (sent(r).body as { group_ids: string[] }).group_ids)).toEqual([
      ['g5', 'g1'],
      ['g5', 'g1'],
    ]);
  });

  it('a group of the card deleted before the card\'s result arrives leaves too, once the refusal names it', async () => {
    const s = await setup({ selected: ['g1'] });
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[1].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    s.net.onApi((r) => ((sent(r).body as { group_ids: string[] }).group_ids.includes('g1') ? groupGone(['g1']) : json({ id: 'c1' })));
    await s.save().trigger('click');
    await flush();
    await s.save().trigger('click');
    await flush();
    expect(s.net.api.map((r) => (sent(r).body as { group_ids: string[] }).group_ids)).toEqual([['g1', 'g2'], ['g2']]);
  });

  it('a ticked group someone else deactivates is no longer seen, and not sent', async () => {
    const s = await setup({ selected: [] });
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[1].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    await s.result(s.call, 'customer.group.list', pageOf([group('g1', 'VIP'), group('g2', 'Staff', false), group('g3', 'Old', false)]));
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([['VIP', false]]);
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    await flush();
    expect((sent(s.net.api[0]).body as { group_ids: string[] }).group_ids).toEqual([]);
  });

  it('an inactive group someone else takes off the card is not put back by saving an untick', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: false } });
    await flush();
    await s.wrapper.setProps({ selected: ['g1'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', false],
      ['Staff', false],
    ]);
    s.net.onApi(() => json({ id: 'c1' }));
    await s.save().trigger('click');
    await flush();
    expect((sent(s.net.api[0]).body as { group_ids: string[] }).group_ids).toEqual([]);
  });

  it('a tick taken back leaves nothing unsaved: it follows the card again', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    const staff = () => s.wrapper.findAllComponents(IonCheckbox)[1];
    staff().vm.$emit('ionChange', { detail: { checked: true } });
    staff().vm.$emit('ionChange', { detail: { checked: false } });
    await flush();
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', true],
      ['Staff', false],
      ['Old (not active)', true],
    ]);
    await s.wrapper.setProps({ selected: ['g2'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', false],
      ['Staff', true],
    ]);
  });

  it('another card starts from its own selection, not from what was ticked on the previous one', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.group.list', GROUPS);
    s.wrapper.findAllComponents(IonCheckbox)[1].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    await s.wrapper.setProps({ customerId: 'c2', selected: ['g1'] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([
      ['VIP', true],
      ['Staff', false],
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

  it('the tags keep an unsaved tick through a live result of the card too (after «Save groups»)', async () => {
    const s = await setup({ kind: 'tags', selected: [] });
    await s.result(s.call, 'customer.tag.list', pageOf([{ id: 't1', name: 'Loyal', color: 'primary', is_active: true, customer_count: 0 }]));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    await s.wrapper.setProps({ selected: [] });
    expect(s.boxes().map((b) => [b[1], b[2]])).toEqual([['Loyal', true]]);
    s.net.onApi(() => json({ id: 'c1' }));
    await s.wrapper.get('[data-testid="customer-tags-save"]').trigger('click');
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/customers/set_tags', body: { id: 'c1', tag_ids: ['t1'] } });
    expect(toastSuccess).toHaveBeenCalledWith('Tags assigned');
  });

  it('the tags: with a search on, after «That tag no longer exists.» only the tag it names leaves', async () => {
    const tag = (id: string, name: string) => ({ id, name, color: 'primary', is_active: true, customer_count: 0 });
    const others = (n: number) => Array.from({ length: n }, (_, i) => tag(`tx${i}`, `Tag ${String(i).padStart(2, '0')}`));
    const s = await setup({ kind: 'tags', selected: [] });
    await s.result(s.call, 'customer.tag.list', pageOf([tag('t1', 'Loyal'), tag('t2', 'New'), ...others(98)], 101));
    let call = await s.search('Loyal', 'tags');
    await s.result(call, 'customer.tag.list', pageOf([tag('t1', 'Loyal')]));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    call = await s.search('New', 'tags');
    await s.result(call, 'customer.tag.list', pageOf([tag('t2', 'New')]));
    s.wrapper.findAllComponents(IonCheckbox)[0].vm.$emit('ionChange', { detail: { checked: true } });
    await flush();
    const tagGone = (ids: string[]) =>
      json({ error: { code: 'customer.tag_unavailable', message: 'That tag no longer exists.', fields: { tags: 'That tag no longer exists.' }, unavailable_ids: ids } }, 422);
    s.net.onApi((r) => ((sent(r).body as { tag_ids: string[] }).tag_ids.includes('t2') ? tagGone(['t2']) : json({ id: 'c1' })));
    const save = () => s.wrapper.get('[data-testid="customer-tags-save"]');
    await save().trigger('click');
    await flush();
    await save().trigger('click');
    await flush();
    expect(s.net.api.map((r) => (sent(r).body as { tag_ids: string[] }).tag_ids)).toEqual([['t1', 't2'], ['t1']]);
    expect(toastSuccess).toHaveBeenCalledWith('Tags assigned');
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

  // flow: customer-searchbar — Ionic 8 names the field of an `ion-searchbar` «search text», in English, whatever its
  // hint says, so a screen reader read «search text» on the card's group and tag search (more than 100 of them).
  it('its search box, once there are more than 100 groups, is named by its hint in the person’s language, never «search text»', async () => {
    const s = await setup({}, { locale: 'es' });
    await s.result(s.call, 'customer.group.list', pageOf([group('g1', 'VIP'), ...OTHER_GROUPS(99)], 140));
    const bar = s.wrapper.get('[data-testid="customer-groups-search"]').element;
    expect(namesGiven(bar).at(-1)).toBe('Buscar grupo…');
    await s.setLocale('en');
    expect(namesGiven(bar).at(-1)).toBe('Search group…');
  });

  it('the tags’ search box is named by its own hint', async () => {
    const tag = (id: string, name: string) => ({ id, name, color: 'primary', is_active: true, customer_count: 0 });
    const s = await setup({ kind: 'tags', selected: [] }, { locale: 'es' });
    await s.result(s.call, 'customer.tag.list', pageOf(Array.from({ length: 100 }, (_, i) => tag(`t${i}`, `Tag ${i}`)), 101));
    const bar = s.wrapper.get('[data-testid="customer-tags-search"]').element;
    expect(namesGiven(bar).at(-1)).toBe('Buscar etiqueta…');
    await s.setLocale('en');
    expect(namesGiven(bar).at(-1)).toBe('Search tag…');
  });
});

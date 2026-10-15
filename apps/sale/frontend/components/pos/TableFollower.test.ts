// The table of the check on screen (SALE-F19): Tables' `table.session.by_order` for that check, followed
// live. Renderless: the page mounts it only while Tables is on, the person may see the table checks and
// there is a check (`useLive` has no «skip»). It hands up the check's seat (its open table check with a
// table, or none) and its parked table check (TABLE-F13), which is seated again rather than opened anew.
import { describe, expect, it } from 'vitest';

import { errorFrame, mountSale } from '../../__tests__/mount-sale';
import TableFollower from './TableFollower.vue';

const OP = 'table.session.by_order';

const tableCheck = (over: Record<string, unknown> = {}) => ({
  id: 's1',
  table_id: 't4',
  table_number: '4',
  zone_id: 'z1',
  zone_name: 'Terrace',
  order_id: 'o1',
  guests_count: 2,
  status: 'open',
  waiter_id: 'u1',
  waiter_name: 'Ana',
  opened_at: '2026-10-15T12:00:00+02:00',
  closed_at: null,
  notes: '',
  split_from_id: null,
  transferred_from_id: null,
  merged_into_id: null,
  paid_total: null,
  customer_id: null,
  customer_name: null,
  ...over,
});

async function setup(orderId = 'o1') {
  const m = await mountSale(TableFollower, { props: { orderId } });
  await m.live();
  return m;
}

describe('TableFollower', () => {
  it('follows the table checks of the check on screen', async () => {
    const m = await setup();
    expect(m.params(OP)).toEqual([{ order_id: 'o1' }]);
  });

  it('hands up its open table check with a table, never a closed or transferred one', async () => {
    const m = await setup();
    const seat = tableCheck();
    await m.result(OP, { rows: [seat, tableCheck({ id: 's0', status: 'closed', table_id: 't2', table_number: '2' })] });
    expect(m.wrapper.emitted('seat')?.at(-1)).toEqual([seat]);
    expect(m.wrapper.emitted('parked')?.at(-1)).toEqual([null]);
  });

  it('a check at no table hands up none', async () => {
    const m = await setup();
    await m.result(OP, { rows: [tableCheck({ status: 'transferred', table_id: null })] });
    expect(m.wrapper.emitted('seat')?.at(-1)).toEqual([null]);
    expect(m.wrapper.emitted('parked')?.at(-1)).toEqual([null]);
  });

  it('a parked table check (the table taken away) is handed up apart, with no seat', async () => {
    const m = await setup();
    const parked = tableCheck({ status: 'parked', table_id: null, table_number: null });
    await m.result(OP, { rows: [parked] });
    expect(m.wrapper.emitted('seat')?.at(-1)).toEqual([null]);
    expect(m.wrapper.emitted('parked')?.at(-1)).toEqual([parked]);
  });

  it('a list that cannot be read hands up nothing', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId(OP), 'permission_denied'));
    await m.reopen();
    expect(m.wrapper.emitted('seat')).toBeUndefined();
  });
});

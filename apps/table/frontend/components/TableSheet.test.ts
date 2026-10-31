// The window of a table in «Service» (WORKBOOK «Plano de sala»; TABLE-F10 to F17, F21, F32):
// - free or reserved: the guests prompt (or «Seat» with the prompt off) and the customer; seating opens its
//   check; a table another device just took says so and stays to pick another;
// - blocked: why it cannot be seated;
// - occupied: guests, since when, who serves, the customer, and Charge (to the till with its check),
//   Transfer, Merge (pick the destination on the plan), Split check, Guests, Remove table and Close table;
//   with two checks, which one first.
import { describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, ionChecked, mountTable, resultFrame, settle } from '../__tests__/mount-table';
import { NOW, occupied, SETTINGS, tableRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import TableSheet from './TableSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const SESSION = { id: 's1', status: 'open' };

async function sheet(
  table: TableOut,
  options: { settings?: Record<string, unknown>; answers?: Record<string, [number, unknown]>; session?: typeof EMPLOYEE; locale?: 'en' | 'es' } = {},
) {
  const m = await mountTable(TableSheet, {
    props: { open: true, table, settings: { ...SETTINGS, ...options.settings }, now: NOW },
    answers: options.answers ?? {},
    session: options.session,
    locale: options.locale,
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const el = (name: string) => m.inDoc(`table-sheet-${name}`) as (HTMLElement & { disabled?: boolean }) | null;
  const guest = (name: string) => m.inDoc(`table-guests-${name}`) as HTMLElement;
  const closed = () => m.wrapper.props('open') === false;
  return { ...m, el, guest, closed };
}

describe('TableSheet · a free or reserved table', () => {
  it('asks the guests with the table’s capacity and seats them, then closes', async () => {
    const s = await sheet(tableRow({ capacity: 6 }), { answers: { '/api/table/sessions/open': [201, SESSION] } });
    expect(s.inDoc('table-sheet')?.getAttribute('aria-label')).toBe('Table 4');
    expect(s.guest('value').textContent?.trim()).toBe('6');
    await click(s.guest('quick-2'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/table/sessions/open', query: {}, body: { table_id: 't1', guests_count: 2 } }]);
    expect(s.closed()).toBe(true);
  });

  it('a reserved table starts from the reservation’s party and shows whose it is', async () => {
    const hold = { label: 'Ana', erased: false, held_from: '2026-10-14T19:30:00Z', held_until: '2026-10-14T21:30:00Z', party_size: 3, reserving: true };
    const s = await sheet(tableRow({ status: 'reserved', hold }));
    expect(s.guest('value').textContent?.trim()).toBe('3');
    expect(s.el('hold')?.textContent).toContain('Reservation: Ana · 9:30 PM · 3 pax');
  });

  it('with the prompt off, «Seat» seats with the table’s capacity in one tap', async () => {
    const s = await sheet(tableRow(), { settings: { prompt_guests_on_seat: false }, answers: { '/api/table/sessions/open': [201, SESSION] } });
    expect(s.inDoc('table-guests')).toBeNull();
    await click(s.el('seat'));
    expect(s.sent().map((call) => call.body)).toEqual([{ table_id: 't1' }]);
  });

  it('a table another device just took says so and stays open to pick another', async () => {
    const taken = { error: { code: 'table.table_not_available', message: 'That table cannot be seated right now.' } };
    const s = await sheet(tableRow(), { answers: { '/api/table/sessions/open': [409, taken] } });
    await click(s.guest('quick-2'));
    expect(s.el('error')?.textContent).toContain('Another device has just taken that table. The floor plan has been refreshed.');
    expect(s.closed()).toBe(false);
  });

  it('seats with the customer picked, and says so when Customers could not put her on the check', async () => {
    const ana = { customer_id: 'c1', customer_name: 'Ana García', customer_tax_id: '', customer_address: '', customer_country: '' };
    const s = await sheet(tableRow(), { answers: { '/api/table/sessions/open': [201, { ...SESSION, customer_id: null }] } });
    s.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', ana);
    await settle();
    await click(s.guest('quick-2'));
    expect(s.sent().map((call) => call.body)).toEqual([{ table_id: 't1', guests_count: 2, customer_id: 'c1' }]);
    expect(s.el('warning')?.textContent).toContain('The table is seated, but the customer could not be put on its check.');
    expect(s.closed()).toBe(false);
  });

  it('a blocked table says why it cannot be seated, with nothing to press', async () => {
    const s = await sheet(tableRow({ status: 'blocked', blocked: true }));
    expect(s.el('blocked')?.textContent).toContain('Table out of service: it cannot be seated until it is unblocked.');
    expect(s.inDoc('table-guests')).toBeNull();
    expect(s.el('seat')).toBeNull();
  });
});

describe('TableSheet · an occupied table', () => {
  it('says the guests, since when and who serves, and Charge goes to the till with its check', async () => {
    const s = await sheet(occupied());
    expect(s.el('summary')?.textContent).toContain('3 guests');
    expect(s.el('summary')?.textContent).toContain('Since 9:05 PM · 35 min');
    expect(s.el('summary')?.textContent).toContain('Served by Luis');
    await click(s.el('action-charge'));
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos?order=o1');
    expect(s.closed()).toBe(true);
  });

  it.each([
    ['en', '1 guest · Since', 'Table 4 · 1 guest. The table is freed'],
    ['es', '1 comensal · Desde', 'Mesa 4 · 1 comensal. La mesa queda libre'],
  ] as const)('one guest is said in the singular (%s, hub#462)', async (locale, summary, impact) => {
    const [check] = occupied().checks;
    const s = await sheet(occupied({ guests: 1, checks: [{ ...check, guests_count: 1 }] }), { locale });
    expect(s.el('summary')?.textContent).toContain(summary);
    await click(s.el('action-close'));
    expect(s.el('close-impact')?.textContent).toContain(impact);
  });

  it('Transfer and Merge pick the destination on the plan', async () => {
    const s = await sheet(occupied());
    await click(s.el('action-transfer'));
    expect(s.wrapper.emitted('pick')?.[0]?.[0]).toMatchObject({ mode: 'transfer', check: { id: 's1' } });
    expect(s.closed()).toBe(true);
  });

  it('corrects the guests', async () => {
    const s = await sheet(occupied(), { answers: { '/api/table/sessions/set_guests': [200, SESSION] } });
    await click(s.el('action-guests'));
    expect(s.guest('value').textContent?.trim()).toBe('3');
    await click(s.guest('more'));
    await click(s.guest('confirm'));
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/sessions/set_guests', { id: 's1', guests_count: 4 }]]);
  });

  it('Remove table parks the check', async () => {
    const s = await sheet(occupied(), { answers: { '/api/table/sessions/park': [200, SESSION] } });
    await click(s.el('action-park'));
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/sessions/park', { id: 's1' }]]);
    expect(s.closed()).toBe(true);
  });

  it('Close table asks first, and a check still open in Sales is refused with the reason', async () => {
    const refused = { error: { code: 'table.session_bill_open', message: 'This table’s bill is still open in Sales.' } };
    const s = await sheet(occupied(), { answers: { '/api/table/sessions/close': [409, refused] } });
    await click(s.el('action-close'));
    expect(s.el('close-impact')?.textContent).toContain('Table 4 · 3 guests. The table is freed');
    await click(s.el('close-confirm'));
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/sessions/close', { id: 's1', order_id: 'o1' }]]);
    expect(s.el('error')?.textContent).toContain('This table’s bill is still open in Sales.');
    expect(s.closed()).toBe(false);
  });

  it('Split check moves the lines marked to a new check', async () => {
    const order = {
      id: 'o1',
      lines: [
        { id: 'l1', name: 'Coffee', quantity: '1', line_total: 150, unit: 'ud' },
        { id: 'l2', name: 'Steak', quantity: '1', line_total: 1800, unit: 'ud' },
      ],
    };
    const s = await sheet(occupied(), { answers: { '/api/table/sessions/split': [200, { session: SESSION, new_session: SESSION }] } });
    await click(s.el('action-split'));
    const stream = await s.live();
    stream.push(resultFrame(s.subId('sale.order.get', { order_id: 'o1' }), order, 1));
    await settle();
    await ionChecked(s.el('split-line-l2'), true);
    await click(s.el('split-confirm'));
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/sessions/split', { id: 's1', line_ids: ['l2'] }]]);
    expect(s.closed()).toBe(true);
  });

  it('with two checks, asks which one first', async () => {
    const table = occupied();
    table.checks = [...table.checks, { ...table.checks[0], id: 's2', order_id: 'o2', guests_count: 1, customer_name: 'Ana García', split_from_id: 's1' }];
    const s = await sheet(table);
    expect(s.el('action-charge')).toBeNull();
    expect(s.el('check-s2')?.textContent).toContain('Ana García');
    await click(s.el('check-s2'));
    await click(s.el('action-charge'));
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos?order=o2');
  });

  it('a live repaint of the same table keeps the step and the choices on screen', async () => {
    // The plan is live: another device changing the room repaints this table (a new row, same id) while the
    // waiter is correcting the guests, splitting or closing; the window must not go back to its first step.
    const s = await sheet(occupied());
    await click(s.el('action-guests'));
    await click(s.guest('more'));
    await s.wrapper.setProps({ table: occupied({ waiter_name: 'Luis' }) });
    await settle();
    expect(s.guest('value').textContent?.trim()).toBe('4');
    await click(s.guest('back'));
    await click(s.el('action-close'));
    await s.wrapper.setProps({ table: occupied() });
    await settle();
    expect(s.el('close-confirm')).not.toBeNull();
    // Another table is another window: it starts over.
    await s.wrapper.setProps({ table: occupied({ id: 't9', number: '9' }) });
    await settle();
    expect(s.el('close-confirm')).toBeNull();
    expect(s.el('action-guests')).not.toBeNull();
  });

  it('a person who may not move checks sees no Transfer nor Merge', async () => {
    const s = await sheet(occupied(), { session: { ...EMPLOYEE, permissions: EMPLOYEE.permissions.filter((p) => p !== 'table.transfer_session') } });
    expect(s.el('action-transfer')).toBeNull();
    expect(s.el('action-merge')).toBeNull();
    expect(s.el('action-guests')).not.toBeNull();
  });
});


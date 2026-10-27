// «Choose table» (SALE-F19; Tables' TABLE-F10, F12, F13): the tables in service searched on the server,
// as tiles in their status colour (number, zone, seats, status, the reservation's name and time); only
// a free or reserved one can be tapped. A tap seats the check on screen there (`table.session.open` with
// its `order_id`), or — with no check yet — lets Tables open one titled with the table; a parked table
// check is seated again (`table.session.restore`). «Remove from table» parks the check's seat. Refusals
// stay in the sheet in the server's words. Sales talks to Tables only through operation names.
import type { SessionMe } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, errorFrame, ionValue, MANAGER, mountSale, settle } from '../../__tests__/mount-sale';
import { namesGiven } from '../../__tests__/searchbar-name';
import { shortTime } from './till';
import TablePicker from './TablePicker.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  syncSearchbarInputName: (await import('../../__tests__/searchbar-name')).recordSearchbarName,
}));

const LIST = 'table.table.list';
const FLOOR = 'table.floor.status';

/** Tables is on and the person sees the tables, seats and changes the table checks. */
const WAITER: SessionMe = {
  ...MANAGER,
  permissions: [...MANAGER.permissions, 'table.view_table', 'table.add_session', 'table.view_session', 'table.change_session'],
  apps: [{ label: 'table', state: 'on' }],
};

const HOLD = {
  label: 'Marta',
  erased: false,
  held_from: '2026-10-15T21:00:00+02:00',
  held_until: '2026-10-15T23:00:00+02:00',
  party_size: 4,
  reserving: true,
};

const table = (over: Record<string, unknown> = {}) => ({
  id: 't1',
  number: '4',
  name: '',
  capacity: 4,
  shape: 'square',
  status: 'available',
  blocked: false,
  is_active: true,
  zone_id: 'z1',
  zone_name: 'Terrace',
  in_service: true,
  position_x: 0,
  position_y: 0,
  width: 80,
  height: 80,
  guests: null,
  since: null,
  waiter_name: '',
  checks: [],
  hold: null,
  ...over,
});

const tableCheck = (over: Record<string, unknown> = {}) => ({
  id: 's1',
  table_id: 't1',
  table_number: '4',
  zone_id: 'z1',
  zone_name: 'Terrace',
  order_id: 'o1',
  guests_count: 4,
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

const page = <T>(rows: T[]) => ({ rows, total: rows.length, limit: 40, offset: 0 });
const FLOOR_SET = { usable_tables: 6, zones: 2 };

async function setup(props: Record<string, unknown> = {}, options: { locale?: 'en' | 'es'; session?: SessionMe } = {}) {
  const open = ref(true);
  const m = await mountSale(
    {
      setup: () => () =>
        h(TablePicker, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), orderId: 'o1', seat: null, parked: null, ...props }),
    },
    { locale: options.locale, session: options.session ?? WAITER },
  );
  await settle();
  await m.live();
  const posts = () => m.sent().filter((c) => c.method === 'POST').map((c) => [c.path, c.body]);
  /** The floor is set up and the tables are these. */
  async function tables(rows: unknown[]) {
    await m.result(FLOOR, FLOOR_SET);
    await m.result(LIST, page(rows));
  }
  return { ...m, open, posts, tables, picker: () => m.wrapper.findComponent(TablePicker) };
}

describe('TablePicker: the tables', () => {
  it('asks the server for the tables in service in number order, and whether the floor is set up', async () => {
    const m = await setup({}, { locale: 'es' });
    expect(m.find('pos-table-title').text()).toBe('Elegir mesa');
    expect(m.params(LIST)).toEqual([{ search: '', in_service: true, sort: 'number', limit: 40, offset: 0 }]);
    expect(m.params(FLOOR)).toEqual([{}]);
    expect(m.find('pos-table-loading').text()).toBe('Cargando mesas…');
  });

  it('paints each table in its status: number, zone, seats, status and the reservation', async () => {
    const m = await setup();
    await m.tables([
      table(),
      table({ id: 't2', number: '5', status: 'occupied', guests: 2 }),
      table({ id: 't3', number: '6', status: 'reserved', hold: HOLD }),
      table({ id: 't4', number: '7', status: 'blocked', blocked: true, zone_name: null }),
    ]);
    const tile = (id: string) => m.find(`pos-table-tile-${id}`);
    /** What the tile says, line by line. */
    const lines = (id: string) => [...tile(id).element.children].map((line) => line.textContent ?? '');
    const time = shortTime(HOLD.held_from, 'en');
    expect(lines('t1')).toEqual(['4', 'Terrace', '4 pax', 'Available']);
    expect(tile('t1').classes()).toContain('pos-table-tile--available');
    expect(tile('t2').classes()).toContain('pos-table-tile--occupied');
    expect(lines('t3')).toEqual(['6', 'Terrace', '4 pax', 'Reserved', `Marta${time}`]);
    expect(tile('t3').findAll('.pos-table-tile__hold span').map((part) => part.text())).toEqual(['Marta', time]);
    expect(tile('t3').attributes('title')).toBe(`Marta (4) · ${time}`);
    expect(lines('t4')).toEqual(['7', '4 pax', 'Blocked']);
  });

  it('only a free or reserved table can be tapped; the others say why', async () => {
    const m = await setup();
    await m.tables([
      table(),
      table({ id: 't2', status: 'occupied' }),
      table({ id: 't3', status: 'reserved' }),
      table({ id: 't4', status: 'blocked' }),
    ]);
    const disabled = (id: string) => (m.find(`pos-table-tile-${id}`).element as HTMLButtonElement).disabled;
    expect([disabled('t1'), disabled('t2'), disabled('t3'), disabled('t4')]).toEqual([false, true, false, true]);
    expect(m.find('pos-table-tile-t2').attributes('title')).toBe('Occupied: another check is at this table.');
    expect(m.find('pos-table-tile-t4').attributes('title')).toBe('Table out of service: it cannot be seated until it is unblocked.');
    await click(m.find('pos-table-tile-t2').element);
    expect(m.posts()).toEqual([]);
  });

  it('marks the table the check is at', async () => {
    const m = await setup({ seat: tableCheck({ table_id: 't2', table_number: '5' }) });
    await m.tables([table(), table({ id: 't2', number: '5', status: 'occupied' })]);
    expect(m.find('pos-table-tile-t2').attributes('aria-pressed')).toBe('true');
    expect(m.find('pos-table-tile-t2').attributes('title')).toBe('This check is at this table.');
    expect(m.find('pos-table-tile-t1').attributes('aria-pressed')).toBe('false');
  });

  it('searches on the server; nothing found is said', async () => {
    const m = await setup();
    await m.tables([table()]);
    await ionValue(m.wrapper.find('ion-searchbar').element, 'ter', 'ionInput');
    await m.reopen();
    expect(m.params(LIST)[0].search).toBe('ter');
    await m.result(LIST, page([]));
    expect(m.find('pos-table-empty').text()).toBe('No table matches your search.');
  });

  it('no table in service is said', async () => {
    const m = await setup();
    await m.tables([]);
    expect(m.find('pos-table-empty').text()).toBe('No table is in service.');
  });

  it('a floor not set up yet says where to set it up', async () => {
    const m = await setup({}, { locale: 'es' });
    await m.result(FLOOR, { usable_tables: 0, zones: 0 });
    await m.result(LIST, page([]));
    expect(m.find('pos-table-unset').text()).toBe('Aún no hay mesas. Créalas en Mesas → Plano de sala.');
    expect(m.wrapper.find('ion-searchbar').exists()).toBe(false);
    expect(m.find('pos-table-empty').exists()).toBe(false);
  });

  it('zones without a usable table are still a floor not set up: it is the tables that count', async () => {
    const m = await setup({}, { locale: 'es' });
    await m.result(FLOOR, { usable_tables: 0, zones: 2 });
    await m.result(LIST, page([]));
    expect(m.find('pos-table-unset').text()).toBe('Aún no hay mesas. Créalas en Mesas → Plano de sala.');
    expect(m.wrapper.find('ion-searchbar').exists()).toBe(false);
  });

  it('usable tables without any zone are a floor set up: the tables are offered, not the notice', async () => {
    const m = await setup();
    await m.result(FLOOR, { usable_tables: 1, zones: 0 });
    await m.result(LIST, page([table({ zone_id: null, zone_name: null })]));
    expect(m.find('pos-table-unset').exists()).toBe(false);
    expect(m.find('pos-table-tile-t1').exists()).toBe(true);
  });

  it('tables that cannot be loaded are said, with «Retry»', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId(LIST), 'internal_error'));
    await m.reopen();
    expect(m.find('pos-table-load-error').text()).toContain('The tables could not be loaded.');
    expect(m.find('pos-table-retry').exists()).toBe(true);
  });
});

describe('TablePicker: seating', () => {
  it('a free table seats the check on screen there, and the sheet closes', async () => {
    const m = await setup();
    await m.tables([table()]);
    const seated = tableCheck();
    m.answer(200, seated);
    await click(m.find('pos-table-tile-t1').element);
    expect(m.posts()).toEqual([['/api/table/sessions/open', { table_id: 't1', order_id: 'o1' }]]);
    expect(m.picker().emitted('seated')).toEqual([[seated]]);
    expect(m.open.value).toBe(false);
  });

  it('with no check yet, Tables opens one for the table: it goes up', async () => {
    const m = await setup({ orderId: null });
    await m.tables([table({ status: 'reserved', hold: HOLD })]);
    const seated = tableCheck({ order_id: 'o9' });
    m.answer(200, seated);
    await click(m.find('pos-table-tile-t1').element);
    expect(m.posts()).toEqual([['/api/table/sessions/open', { table_id: 't1' }]]);
    expect(m.picker().emitted('seated')).toEqual([[seated]]);
  });

  it('a check whose table was taken away is seated again, not opened anew', async () => {
    const m = await setup({ parked: tableCheck({ id: 's7', status: 'parked', table_id: null, table_number: null }) });
    await m.tables([table()]);
    m.answer(200, tableCheck({ id: 's7' }));
    await click(m.find('pos-table-tile-t1').element);
    expect(m.posts()).toEqual([['/api/table/sessions/restore', { id: 's7', table_id: 't1' }]]);
    expect(m.open.value).toBe(false);
  });

  it('a refusal stays in the sheet in the server’s words; one it did not word says the screen’s', async () => {
    const m = await setup();
    await m.tables([table()]);
    m.answer(409, { error: { code: 'table.table_not_available', message: 'Another device has just taken that table.' } });
    await click(m.find('pos-table-tile-t1').element);
    expect(m.find('pos-table-error').text()).toBe('Another device has just taken that table.');
    expect(m.open.value).toBe(true);
    expect(m.picker().emitted('seated')).toBeUndefined();
    m.answer(500, { error: { code: 'internal_error', message: 'Boom' } });
    await click(m.find('pos-table-tile-t1').element);
    expect(m.find('pos-table-error').text()).toBe('The check could not be seated at that table.');
  });
});

describe('TablePicker: removing the table', () => {
  it('«Remove from table» is there only when the check has a table and the person may change it', async () => {
    const none = await setup();
    expect(none.find('pos-table-remove').exists()).toBe(false);
    const seat = tableCheck();
    const blind = await setup({ seat }, { session: { ...WAITER, permissions: WAITER.permissions.filter((p) => p !== 'table.change_session') } });
    expect(blind.find('pos-table-remove').exists()).toBe(false);
    const m = await setup({ seat }, { locale: 'es' });
    expect(m.find('pos-table-remove').text()).toBe('Quitar de la mesa');
  });

  it('parks the check’s seat: the table frees and the sheet closes', async () => {
    const m = await setup({ seat: tableCheck({ id: 's3' }) });
    m.answer(200, tableCheck({ id: 's3', status: 'parked', table_id: null }));
    await click(m.find('pos-table-remove').element);
    expect(m.posts()).toEqual([['/api/table/sessions/park', { id: 's3' }]]);
    expect(m.open.value).toBe(false);
  });

  it('a refused removal stays in the sheet', async () => {
    const m = await setup({ seat: tableCheck({ id: 's3' }) });
    m.answer(409, { error: { code: 'table.session_not_open', message: 'That check is not open.' } });
    await click(m.find('pos-table-remove').element);
    expect(m.find('pos-table-error').text()).toBe('That check is not open.');
    expect(m.open.value).toBe(true);
  });
});

describe('TablePicker: its search box', () => {
  it('is named by its hint in the person’s language, never Ionic’s English «search text»', async () => {
    const m = await setup({}, { locale: 'es' });
    const bar = m.wrapper.find('ion-searchbar').element;
    expect(namesGiven(bar).at(-1)).toBe('Buscar mesa…');
    await m.setLocale('en');
    expect(namesGiven(bar).at(-1)).toBe('Search a table…');
  });

  it('a search box that comes back (the floor set up meanwhile) is named too', async () => {
    const m = await setup({}, { locale: 'es' });
    await m.result(FLOOR, { usable_tables: 0, zones: 0 });
    expect(m.wrapper.find('ion-searchbar').exists()).toBe(false);
    await m.result(FLOOR, FLOOR_SET, {}, 2);
    expect(namesGiven(m.wrapper.find('ion-searchbar').element)).toEqual(['Buscar mesa…']);
  });
});

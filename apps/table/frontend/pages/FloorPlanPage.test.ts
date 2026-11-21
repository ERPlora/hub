// Tables → Floor plan: one row on top — the zone strip and, for whoever draws the room, «Service / Edit plan»,
// the «+» and the pencil — a summary of the chosen zone, and its live plan underneath (on a phone in
// «Service», its cards): every table of the room is read once, on the page's one stream, and the strip only
// picks which zone the plan paints.
// - Service: the zones and tables in service; a tap on an occupied table opens its check in Sales (a split
//   one asks which check first), a tap on any other table and a long press on any table open its window;
//   Transfer and Merge pick their destination on the plan («Transfer 4 to…», «Pick a free table», «Cancel»).
// - Edit plan: every zone and table (the inactive ones greyed out); a tap opens «Edit table», a drag saves
//   the place at once (a refused one goes back and says so); «+» adds a zone or a table, the pencil edits
//   the zone.
import { FloorCards } from '@erplora/ui/components';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, flush, type MountOptions, mountTable, page, settle } from '../__tests__/mount-table';
import { occupied, SETTINGS, tableRow, zoneRow } from '../__tests__/tables';
import AddModal from '../components/AddModal.vue';
import FloorCanvas from '../components/FloorCanvas.vue';
import TableFormModal from '../components/TableFormModal.vue';
import TableSheet from '../components/TableSheet.vue';
import ZoneFormModal from '../components/ZoneFormModal.vue';
import type { TableOut } from '../operations';
import FloorPlanPage from './FloorPlanPage.vue';

const TABLES = 'table.table.list';
const ZONES = [zoneRow({ id: 'z1', name: 'Dining room' }), zoneRow({ id: 'z2', name: 'Terrace', sort_order: 1 }), zoneRow({ id: 'z3', name: 'Old bar', is_active: false })];
const FREE = tableRow({ id: 't1', number: '1' });
const BUSY = occupied({ id: 't4', number: '4', position_x: 104 });
const IDLE = tableRow({ id: 't9', number: '9', is_active: false, in_service: false, position_x: 192 });
const TERRACE = tableRow({ id: 't7', number: '7', zone_id: 'z2', zone_name: 'Terrace' });

/** Table 4 split in two checks; the second one's order is `o2`. */
function splitTable(): TableOut {
  const table = occupied({ id: 't4', number: '4' });
  table.checks = [...table.checks, { ...table.checks[0], id: 's2', order_id: 'o2' }];
  return table;
}

/** A screen of `width` px: `@erplora/ui`'s phone breakpoint answers as a browser would. */
function screenOf(width: number): void {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(max-width: 640px)' && width <= 640,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

async function setup(options: MountOptions = {}) {
  const m = await mountTable(FloorPlanPage, { path: '/table/floor-plan', ...options });
  await m.live();
  const el = (name: string) => m.wrapper.find(`[data-testid="table-floor-${name}"]`);
  const tiles = () => m.wrapper.findAll('[data-testid^="table-floor-tile-"]').map((tile) => tile.attributes('data-testid')!.replace('table-floor-tile-', ''));
  const show = async (zones = ZONES, tables: TableOut[] = [FREE, BUSY, IDLE, TERRACE]) => {
    await m.result('table.settings.get', SETTINGS);
    await m.result('table.zone.list', page(zones));
    await flush();
    await m.reopen();
    await m.result(TABLES, page(tables, tables.length, 100));
  };
  const mode = async (value: 'service' | 'edit') => {
    el('mode').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true }));
    await flush();
  };
  const canvas = () => m.wrapper.findComponent(FloorCanvas);
  /** The labels of a segment's buttons (Ionic's own element hides its light DOM from \`text()\`). */
  const labels = (prefix: string) => m.wrapper.findAll(`[data-testid^="${prefix}"]`).map((button) => button.find('ion-label').element.innerHTML.trim());
  const zoneNames = () => m.wrapper.findAll('[data-testid^="table-floor-zone-tab-"] [data-part="zone-name"]').map((name) => name.text());
  return { ...m, el, tiles, show, mode, canvas, labels, zoneNames };
}

describe('FloorPlanPage · service', () => {
  it('follows the zones and the whole room on one stream, and paints the first zone in service', async () => {
    const s = await setup();
    await s.show();
    expect(s.params('table.zone.list')).toEqual([{ sort: 'sort_order', limit: 100 }]);
    // Asked before the zones arrive: a query that waited for them would change once they came, and the
    // SDK would throw the page's first stream away (an aborted /api/live on every visit).
    expect(s.params(TABLES)).toEqual([{ sort: 'number', limit: 100, offset: 0 }]);
    expect(s.net.streams.map((stream) => stream.aborted())).toEqual([false]);
    expect(s.zoneNames()).toEqual(['Dining room', 'Terrace']);
    expect(s.tiles()).toEqual(['t1', 't4']);
    expect(s.el('hint').text()).toBe('Tap a table to seat it or open its check · press and hold it (or right-click it) for transfer, merge and more.');
  });

  it('shows a skeleton of the plan while it loads, then each zone tab counts its occupied tables and the card sums up the zone', async () => {
    const s = await setup();
    expect(s.el('loading').attributes('role')).toBe('progressbar');
    expect(s.el('loading').classes()).toContain('floor-skeleton--plan');
    expect(s.el('summary').exists()).toBe(false);
    await s.show();
    expect(s.el('loading').exists()).toBe(false);
    const counts = s.wrapper.findAll('[data-part="zone-count"]').map((count) => count.text());
    expect(counts).toEqual(['1/2', '0/1']);
    expect(s.el('summary').find('h2').text()).toBe('Dining room');
    expect(s.el('summary').find('[data-stat="occupied"]').text()).toBe('1Occupied');
    expect(s.el('summary').find('[data-stat="guests"]').text()).toBe('3Guests');
  });

  it('names the skeleton, the strip, the summary and the cards in the app’s language', async () => {
    screenOf(390);
    const s = await setup({ locale: 'es' });
    expect(s.el('loading').attributes('aria-label')).toBe('Cargando el plano de sala');
    expect(s.el('loading').classes()).toContain('floor-skeleton--cards');
    await s.show();
    expect(s.el('zones').attributes('aria-label')).toBe('Zonas');
    expect(s.wrapper.find('[data-testid="table-floor-zone-tab-z1"] [data-part="zone-count-said"]').text()).toBe('1 de 2 mesas ocupadas');
    expect(s.el('summary').attributes('aria-label')).toBe('Resumen de la zona');
    expect(s.el('summary').find('[data-part="occupied-of"]').text()).toBe('1 de 2 mesas ocupadas');
    expect(s.el('summary').find('[data-stat="available"]').text()).toBe('1Disponibles');
    expect(s.el('cards').attributes('aria-label')).toBe('Mesas por número');
    expect(s.wrapper.find('[data-testid="table-floor-tile-t4"] [data-part="status"]').text()).toBe('Ocupada');
  });

  it('on a phone lists the zone as cards, and the plan comes back to edit it', async () => {
    screenOf(390);
    const s = await setup();
    await s.show();
    expect(s.el('cards').exists()).toBe(true);
    expect(s.el('canvas').exists()).toBe(false);
    expect(s.tiles()).toEqual(['t1', 't4']);
    s.wrapper.findComponent(FloorCards).vm.$emit('select', 't4');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos?order=o1');
    s.wrapper.findComponent(FloorCards).vm.$emit('actions', 't4');
    await flush();
    const sheet = s.wrapper.findComponent(TableSheet);
    expect([sheet.props('open'), (sheet.props('table') as TableOut).id, sheet.props('intent')]).toEqual([true, 't4', 'actions']);
    await s.mode('edit');
    expect(s.el('cards').exists()).toBe(false);
    expect(s.el('canvas').exists()).toBe(true);
  });

  it('on a phone a transfer picks its destination among the cards, where a long press does nothing', async () => {
    screenOf(390);
    const s = await setup();
    await s.show();
    s.wrapper.findComponent(TableSheet).vm.$emit('pick', { mode: 'transfer', table: BUSY, check: BUSY.checks[0] });
    await flush();
    const card = (id: string) => s.wrapper.find(`[data-testid="table-floor-tile-${id}"]`).classes();
    expect(card('t4')).toContain('floor-card--dimmed');
    expect(card('t1')).toContain('floor-card--target');
    s.wrapper.findComponent(FloorCards).vm.$emit('actions', 't1');
    await flush();
    expect(s.wrapper.findComponent(TableSheet).props('open')).toBe(false);
    expect(s.el('pick').exists()).toBe(true);
    expect(s.el('hint').exists()).toBe(false);
  });

  it('a tablet keeps the plan', async () => {
    screenOf(834);
    const s = await setup();
    await s.show();
    expect([s.el('canvas').exists(), s.el('cards').exists()]).toEqual([true, false]);
  });

  it('tells apart, on the plan and on a phone, the occupied table that asked for its bill', async () => {
    const asked = occupied({ id: 't5', number: '5', position_x: 192, bill_requested: true });
    let s = await setup({ locale: 'es' });
    const bill = (id: string) => s.wrapper.find(`[data-testid="table-floor-tile-${id}"]`).attributes('data-bill');
    const status = (id: string) => s.wrapper.find(`[data-testid="table-floor-tile-${id}"] [data-part="status"]`).text();
    await s.show(ZONES, [FREE, BUSY, asked]);
    expect([bill('t5'), bill('t4'), bill('t1')]).toEqual(['requested', undefined, undefined]);
    expect([status('t5'), status('t4')]).toEqual(['Cuenta pedida · 3/4 pax', 'Ocupada · 3/4 pax']);
    expect(s.el('summary').find('[data-stat="occupied"]').text()).toBe('2Ocupadas');
    screenOf(390);
    s = await setup({ locale: 'es' });
    await s.show(ZONES, [FREE, BUSY, asked]);
    expect([bill('t5'), bill('t4'), bill('t1')]).toEqual(['requested', undefined, undefined]);
    expect([status('t5'), status('t4')]).toEqual(['Cuenta pedida', 'Ocupada']);
  });

  it('another zone of the strip shows its plan at once, without asking the server again', async () => {
    const s = await setup();
    await s.show();
    s.el('zones').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'z2' }, bubbles: true }));
    await flush();
    await s.reopen();
    expect(s.tiles()).toEqual(['t7']);
    expect(s.net.streams.length).toBe(1);
  });

  it('the zone strip fades the edge with more zones behind it', async () => {
    const s = await setup();
    await s.show();
    const strip = s.el('zones').element;
    Object.defineProperty(strip, 'clientWidth', { configurable: true, value: 300 });
    Object.defineProperty(strip, 'scrollWidth', { configurable: true, value: 700 });
    Object.defineProperty(strip, 'scrollLeft', { configurable: true, writable: true, value: 0 });
    strip.dispatchEvent(new Event('scroll'));
    await flush();
    expect(s.el('zones').classes()).toContain('floor-zone-tabs--more-right');
    expect(s.el('zones').classes()).not.toContain('floor-zone-tabs--more-left');
  });

  it('a tap on an occupied table opens its check in Sales, with no window on the way', async () => {
    const s = await setup();
    await s.show();
    s.canvas().vm.$emit('select', BUSY);
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos?order=o1');
    expect(s.wrapper.findComponent(TableSheet).props('open')).toBe(false);
  });

  it('a long press opens the table’s window with its actions, which follows the live table', async () => {
    const s = await setup();
    await s.show();
    s.canvas().vm.$emit('actions', BUSY);
    await flush();
    const sheet = s.wrapper.findComponent(TableSheet);
    expect([sheet.props('open'), (sheet.props('table') as TableOut).id, sheet.props('intent')]).toEqual([true, 't4', 'actions']);
    expect(s.router.currentRoute.value.fullPath).toBe('/table/floor-plan');
    await s.result(TABLES, page([FREE, { ...BUSY, guests: 5 }, IDLE, TERRACE], 4, 100));
    expect((s.wrapper.findComponent(TableSheet).props('table') as TableOut).guests).toBe(5);
  });

  it('a tap on a free table opens its window to seat it, as does one on a check that Sales has not got', async () => {
    const orderless = occupied({ id: 't5', number: '5', position_x: 192 });
    orderless.checks = [{ ...orderless.checks[0], order_id: null }];
    const s = await setup();
    await s.show(ZONES, [FREE, orderless]);
    for (const table of [FREE, orderless]) {
      s.canvas().vm.$emit('select', table);
      await flush();
      const sheet = s.wrapper.findComponent(TableSheet);
      expect([sheet.props('open'), (sheet.props('table') as TableOut).id, sheet.props('intent')]).toEqual([true, table.id, 'actions']);
    }
    expect(s.router.currentRoute.value.fullPath).toBe('/table/floor-plan');
  });

  it('a tap on a split table asks which check first, and the one chosen opens in Sales', async () => {
    const split = splitTable();
    const s = await setup();
    await s.show(ZONES, [split]);
    s.canvas().vm.$emit('select', split);
    await flush();
    const sheet = s.wrapper.findComponent(TableSheet);
    expect([sheet.props('open'), sheet.props('intent')]).toEqual([true, 'check']);
    sheet.vm.$emit('check', 'o2');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos?order=o2');
  });

  it('Transfer picks a free table on the plan, then moves the check there', async () => {
    const s = await setup();
    await s.show();
    s.wrapper.findComponent(TableSheet).vm.$emit('pick', { mode: 'transfer', table: BUSY, check: BUSY.checks[0] });
    await flush();
    expect(s.el('pick').text()).toContain('Transfer 4 to…');
    expect(s.el('pick').text()).toContain('Pick a free table');
    const pick = s.canvas().props('pick') as (table: TableOut) => boolean;
    expect([pick(FREE), pick(BUSY)]).toEqual([true, false]);
    s.answer(200, { id: 's9' });
    s.canvas().vm.$emit('select', FREE);
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/table/sessions/transfer', query: {}, body: { id: 's1', to_table_id: 't1' } }]);
    expect(s.el('pick').exists()).toBe(false);
  });

  it('Merge into the other check of a split table names that check; «Cancel» stops picking', async () => {
    const split = splitTable();
    const s = await setup();
    await s.show(ZONES, [split]);
    s.wrapper.findComponent(TableSheet).vm.$emit('pick', { mode: 'merge', table: split, check: split.checks[1] });
    await flush();
    expect(s.el('pick').text()).toContain('Merge 4 with…');
    s.answer(200, { id: 's1' });
    s.canvas().vm.$emit('select', split);
    await flush();
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 's2', into_session_id: 's1' }]);
    s.wrapper.findComponent(TableSheet).vm.$emit('pick', { mode: 'merge', table: split, check: split.checks[1] });
    await flush();
    await click(s.el('pick-cancel').element);
    expect(s.el('pick').exists()).toBe(false);
  });

  it('a destination another device just took says so', async () => {
    const s = await setup();
    await s.show();
    s.wrapper.findComponent(TableSheet).vm.$emit('pick', { mode: 'transfer', table: BUSY, check: BUSY.checks[0] });
    await flush();
    s.answer(409, { error: { code: 'table.table_not_available', message: 'Taken.' } });
    s.canvas().vm.$emit('select', FREE);
    await flush();
    expect(s.el('error').text()).toContain('Another device has just taken that table. The floor plan has been refreshed.');
  });

  it('a reservation entering its window repaints its table by the clock and asks the server again', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    try {
      vi.setSystemTime(new Date('2026-10-14T19:58:00Z'));
      const s = await setup();
      const hold = { label: 'Ana', erased: false, held_from: '2026-10-14T21:00:00Z', held_until: '2026-10-14T23:00:00Z', party_size: 4, reserving: false };
      await s.show(ZONES, [tableRow({ id: 't1', number: '1', hold })]);
      const tileOf = () => s.wrapper.find('[data-testid="table-floor-tile-t1"]');
      expect(tileOf().attributes('data-status')).toBe('available');
      const streams = s.net.streams.length;
      await vi.advanceTimersByTimeAsync(3 * 60_000);
      await flush();
      expect(tileOf().attributes('data-status')).toBe('reserved');
      await s.reopen();
      expect(s.net.streams.length).toBeGreaterThan(streams);
    } finally {
      vi.useRealTimers();
    }
  });

  it('a waiter sees no «Edit plan», no «+» and no pencil', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show();
    expect([s.el('mode').exists(), s.el('add').exists(), s.el('zone-edit').exists()]).toEqual([false, false, false]);
  });

  it('without zones says how to start; a zone without tables in service says so', async () => {
    const empty = await setup({ session: EMPLOYEE });
    await empty.show([], []);
    expect(empty.el('empty-zones').text()).toContain('Create a zone to start placing tables.');
    const none = await setup({ session: EMPLOYEE });
    await none.show(ZONES, [IDLE]);
    expect(none.el('empty-tables').text()).toContain('No tables in service in this zone.');
    expect(none.el('hint').exists()).toBe(false);
  });
});

describe('FloorPlanPage · edit plan', () => {
  it('shows every zone and table, the hint, and a tap opens «Edit table»', async () => {
    const s = await setup();
    await s.show();
    await s.mode('edit');
    expect(s.zoneNames()).toEqual(['Dining room', 'Terrace', 'Old bar']);
    expect(s.tiles()).toEqual(['t1', 't4', 't9']);
    expect(s.el('hint').text()).toBe('Drag to position · click a table to edit or delete it. Changes are saved instantly.');
    s.canvas().vm.$emit('select', FREE);
    await flush();
    const form = s.wrapper.findComponent(TableFormModal);
    expect([form.props('open'), (form.props('table') as TableOut).id]).toEqual([true, 't1']);
  });

  it('a drag saves the place at once; a refused one goes back and says so', async () => {
    const s = await setup();
    await s.show();
    await s.mode('edit');
    s.answer(200, FREE);
    s.canvas().vm.$emit('move', { table: FREE, x: 200, y: 120 });
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/table/tables/move', query: {}, body: { id: 't1', position_x: 200, position_y: 120 } }]);
    const revert = vi.spyOn((s.canvas().vm as unknown as { $: { exposed: { revert(id: string): void } } }).$.exposed, 'revert');
    s.answer(403, { error: { code: 'permission_denied', message: 'No.' } });
    s.canvas().vm.$emit('move', { table: FREE, x: 300, y: 120 });
    await flush();
    await settle();
    expect(s.el('error').text()).toContain('Could not save the position');
    expect(revert).toHaveBeenCalledWith('t1');
  });

  it('«+» adds a zone or a table, and a new zone becomes the chosen one; the pencil edits the zone', async () => {
    const s = await setup();
    await s.show();
    await s.mode('edit');
    await click(s.el('add').element);
    const add = s.wrapper.findComponent(AddModal);
    expect([add.props('open'), add.props('zoneId')]).toEqual([true, 'z1']);
    add.vm.$emit('zone', 'z2');
    await flush();
    expect(s.tiles()).toEqual(['t7']);
    await click(s.el('zone-edit').element);
    const zone = s.wrapper.findComponent(ZoneFormModal);
    expect([zone.props('open'), (zone.props('zone') as { id: string }).id, zone.props('variant')]).toEqual([true, 'z2', 'plan']);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show();
    expect(s.labels('table-floor-mode-')).toEqual(['Servicio', 'Editar plano']);
    expect(s.el('hint').text()).toBe('Toca una mesa para sentarla o abrir su cuenta · mantenla pulsada (o haz clic derecho) para transferir, fusionar y más.');
    await s.mode('edit');
    expect(s.el('hint').text()).toBe('Arrastra para colocar · clic en una mesa para editarla o borrarla. Los cambios se guardan al momento.');
  });
});

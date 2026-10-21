// Tables → Floor plan (WORKBOOK «Pantallas · Plano de sala»; TABLE-F01 to F06, F09 to F17): one row on
// top — the zone strip and, for whoever draws the room, «Service / Edit plan», the «+» and the pencil —
// and the live plan of the chosen zone underneath: every table of the room is read once, on the page's one
// stream, and the strip only picks which zone the plan paints.
// - Service: the zones and tables in service; a tap opens the table's window; Transfer and Merge pick
//   their destination on the plan («Transfer 4 to…», «Pick a free table», «Cancel»).
// - Edit plan: every zone and table (the inactive ones greyed out); a tap opens «Edit table», a drag saves
//   the place at once (a refused one goes back and says so); «+» adds a zone or a table, the pencil edits
//   the zone.
import { describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, flush, type MountOptions, mountTable, page, settle } from '../__tests__/mount-table';
import { occupied, SETTINGS, tableRow, zoneRow } from '../__tests__/tables';
import AddModal from '../components/AddModal.vue';
import FloorCanvas from '../components/FloorCanvas.vue';
import TableFormModal from '../components/TableFormModal.vue';
import TableSheet from '../components/TableSheet.vue';
import ZoneFormModal from '../components/ZoneFormModal.vue';
import type { TableOut } from '../operations';
import FloorPlanPage from './FloorPlanPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const TABLES = 'table.table.list';
const ZONES = [zoneRow({ id: 'z1', name: 'Dining room' }), zoneRow({ id: 'z2', name: 'Terrace', sort_order: 1 }), zoneRow({ id: 'z3', name: 'Old bar', is_active: false })];
const FREE = tableRow({ id: 't1', number: '1' });
const BUSY = occupied({ id: 't4', number: '4', position_x: 104 });
const IDLE = tableRow({ id: 't9', number: '9', is_active: false, in_service: false, position_x: 192 });
const TERRACE = tableRow({ id: 't7', number: '7', zone_id: 'z2', zone_name: 'Terrace' });

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
  return { ...m, el, tiles, show, mode, canvas, labels };
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
    expect(s.labels('table-floor-zone-tab-')).toEqual(['Dining room', 'Terrace']);
    expect(s.tiles()).toEqual(['t1', 't4']);
    expect(s.el('hint').exists()).toBe(false);
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

  it('the zone strip fades the edge with more zones behind it (tables#97)', async () => {
    const s = await setup();
    await s.show();
    const strip = s.el('zones').element;
    Object.defineProperty(strip, 'clientWidth', { configurable: true, value: 300 });
    Object.defineProperty(strip, 'scrollWidth', { configurable: true, value: 700 });
    Object.defineProperty(strip, 'scrollLeft', { configurable: true, writable: true, value: 0 });
    strip.dispatchEvent(new Event('scroll'));
    await flush();
    expect(s.el('zones').classes()).toContain('table-floor__zones--more-right');
    expect(s.el('zones').classes()).not.toContain('table-floor__zones--more-left');
  });

  it('a tap opens the table’s window, which follows the live table', async () => {
    const s = await setup();
    await s.show();
    s.canvas().vm.$emit('select', BUSY);
    await flush();
    const sheet = s.wrapper.findComponent(TableSheet);
    expect([sheet.props('open'), (sheet.props('table') as TableOut).id]).toEqual([true, 't4']);
    await s.result(TABLES, page([FREE, { ...BUSY, guests: 5 }, IDLE, TERRACE], 4, 100));
    expect((s.wrapper.findComponent(TableSheet).props('table') as TableOut).guests).toBe(5);
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
    const split = occupied({ id: 't4', number: '4' });
    split.checks = [...split.checks, { ...split.checks[0], id: 's2', order_id: 'o2' }];
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
  });
});

describe('FloorPlanPage · edit plan', () => {
  it('shows every zone and table, the hint, and a tap opens «Edit table»', async () => {
    const s = await setup();
    await s.show();
    await s.mode('edit');
    expect(s.labels('table-floor-zone-tab-')).toEqual(['Dining room', 'Terrace', 'Old bar']);
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
    await s.mode('edit');
    expect(s.el('hint').text()).toBe('Arrastra para colocar · clic en una mesa para editarla o borrarla. Los cambios se guardan al momento.');
  });
});

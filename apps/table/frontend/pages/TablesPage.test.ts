// Tables → Tables (WORKBOOK «Pantallas · Mesas»; TABLE-F02, F04): the live `table.table.list` in natural
// order (2 before 10, from the server) — Number, Name, Zone, Capacity and Status —, «Search table…»,
// column filters (zone, capacity, status), list or cards, 50 a page. «+» opens «New table» (Number,
// Capacity, Zone); Edit and a row open «Edit table»; Delete (owner and admin) asks first.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, flush, MANAGER, type MountOptions, mountTable, page } from '../__tests__/mount-table';
import { occupied, tableRow, zoneRow } from '../__tests__/tables';
import TableFormModal from '../components/TableFormModal.vue';
import TablesPage from './TablesPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'table.table.list';
const ROWS = [tableRow({ id: 't2', number: '2', name: 'Window' }), occupied({ id: 't10', number: '10', zone_name: 'Terrace', zone_id: 'z2' })];
const ZONES = [zoneRow(), zoneRow({ id: 'z2', name: 'Terrace' })];

async function setup(options: MountOptions = {}) {
  const m = await mountTable(TablesPage, { path: '/table/tables', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="table-tables-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const show = async (data: unknown) => {
    await m.result('table.zone.list', page(ZONES));
    await m.result(OP, data);
  };
  return { ...m, table, prop, rows, cells, list: () => m.params(OP), show };
}

describe('TablesPage', () => {
  it('follows the tables in natural order with Number, Name, Zone, Capacity and Status', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'number', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Search table…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New table');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['number', 'Number'],
      ['name', 'Name'],
      ['zone_name', 'Zone'],
      ['capacity', 'Capacity'],
      ['status', 'Status'],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['2', 'Window', 'Dining room', '4', 'Available']);
    expect(s.cells(1).slice(0, 5)).toEqual(['10', '—', 'Terrace', '4', 'Occupied']);
  });

  it('searches, filters by zone, capacity and status, and sorts on the server; none says «No tables.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No tables.');
    const zone = s.prop<Array<{ key: string; filter?: { options?: Array<{ value: string; label: string }> } }>>('columns').find((c) => c.key === 'zone_name');
    expect(zone?.filter?.options).toEqual([
      { value: 'z1', label: 'Dining room' },
      { value: 'z2', label: 'Terrace' },
    ]);
    s.table().vm.$emit('sortChange', { sort: 'capacity', dir: 'desc' });
    s.table().vm.$emit('update:search', '1');
    s.table().vm.$emit('filtersChange', { zone_id: 'z2', status: 'occupied', capacity_from: '2', capacity_to: '6' });
    await flush();
    expect(s.list()).toEqual([
      { search: '1', sort: '-capacity', zone_id: 'z2', status: 'occupied', capacity_min: 2, capacity_max: 6, limit: 50, offset: 0 },
    ]);
  });

  it('«New table», Edit and a row open the table’s dialog', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const modal = () => s.wrapper.findComponent(TableFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('table'), modal().props('zones')]).toEqual([true, null, ZONES]);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect([modal().props('open'), modal().props('table')]).toEqual([true, ROWS[1]]);
  });

  it('deletes after its confirmation', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[0] });
    await flush();
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === 'table-tables-delete');
    expect([dialog?.props('title'), dialog?.props('message'), dialog?.props('confirmLabel')]).toEqual([
      'Delete table 2?',
      'It leaves the plan and the lists; its history of checks stays.',
      'Delete table',
    ]);
    s.answer(200, { id: 't2' });
    dialog?.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/table/tables/delete', query: {}, body: { id: 't2' } }]);
  });

  it('a manager adds and edits but does not delete; a waiter only reads', async () => {
    const manager = await setup({ session: MANAGER });
    await manager.show(page(ROWS));
    expect(manager.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['edit']);
    const employee = await setup({ session: EMPLOYEE });
    await employee.show(page(ROWS));
    expect([employee.prop('addable'), employee.prop('rowClickable'), employee.prop<unknown[]>('actions')]).toEqual([false, false, []]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar mesa…', 'Nueva mesa']);
    expect(s.cells(1)[4]).toBe('Ocupada');
  });
});

// Tables → Zones (WORKBOOK «Pantallas · Zonas»; TABLE-F01, F06): the live `table.zone.list` by Order —
// Name (with its colour), Tables, Free («free / total»), Order and Status (Active, Inactive) —, «Search
// zone…», column filters, list or cards, 50 a page. «+» (whoever may add) and Edit open the zone's dialog;
// Delete (owner and admin) asks first and is off for a zone with tables.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, flush, MANAGER, type MountOptions, mountTable, page } from '../__tests__/mount-table';
import { zoneRow } from '../__tests__/tables';
import ZoneDeleteDialog from '../components/ZoneDeleteDialog.vue';
import ZoneFormModal from '../components/ZoneFormModal.vue';
import ZonesPage from './ZonesPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'table.zone.list';
const ROWS = [
  zoneRow({ id: 'z1', name: 'Terrace', color: 'success', sort_order: 0, table_count: 6, available_count: 4 }),
  zoneRow({ id: 'z2', name: 'Bar', sort_order: 1, is_active: false }),
];

async function setup(options: MountOptions = {}) {
  const m = await mountTable(ZonesPage, { path: '/table/zones', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="table-zones-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, prop, rows, cells, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('ZonesPage', () => {
  it('follows the zones by their order with Name, Tables, Free, Order and Status', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'sort_order', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Search zone…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New zone');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['table_count', 'Tables'],
      ['available_count', 'Free'],
      ['sort_order', 'Order'],
      ['is_active', 'Status'],
      ['color', 'Colour'],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['Terrace', '6', '4 / 6', '0', 'Active']);
    expect(s.cells(1).slice(0, 5)).toEqual(['Bar', '0', '0 / 0', '1', 'Inactive']);
  });

  it('searches, filters and sorts on the server; none at all says how to start', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No zones. Tap «+» to create the first one (Dining room, Terrace, Bar…).');
    s.table().vm.$emit('sortChange', { sort: 'name', dir: 'desc' });
    s.table().vm.$emit('update:search', 'ter');
    s.table().vm.$emit('filtersChange', { is_active: 'false', color: 'success' });
    await flush();
    expect(s.list()).toEqual([{ search: 'ter', sort: '-name', is_active: false, color: 'success', limit: 50, offset: 0 }]);
  });

  it('«New zone» and Edit open the zone’s dialog; Delete asks first', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const modal = () => s.wrapper.findComponent(ZoneFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('zone')]).toEqual([true, null]);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('action', { actionId: 'edit', row: ROWS[1] });
    await flush();
    expect([modal().props('open'), modal().props('zone'), modal().props('variant')]).toEqual([true, ROWS[1], 'full']);
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[0] });
    await flush();
    const dialog = s.wrapper.findAllComponents(ZoneDeleteDialog).find((d) => d.props('testid') === 'table-zones-delete');
    expect([dialog?.props('open'), dialog?.props('zone')]).toEqual([true, ROWS[0]]);
  });

  it('a manager adds and edits but does not delete; an employee only reads', async () => {
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
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar zona…', 'Nueva zona']);
    expect(s.cells(0).slice(0, 5)).toEqual(['Terrace', '6', '4 / 6', '0', 'Activa']);
  });
});

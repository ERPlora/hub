// «Edit table» and «New table» (WORKBOOK «Plano de sala», «Mesas»; TABLE-F02, F04, F05): Number,
// Capacity, Name (optional), Shape, Status (Available or Blocked: the others are the room's, not a
// person's), Zone and In use; «Save» sends only what changed; «Delete» (whoever may) asks first. A new
// table asks Number (empty = the first free one), Capacity and Zone. Refusals stay in the dialog.
import { describe, expect, it, vi } from 'vitest';

import { click, ionChecked, ionValue, mountTable, settle } from '../__tests__/mount-table';
import { tableRow, zoneRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import TableFormModal from './TableFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; disabled?: boolean };

const ZONES = [zoneRow(), zoneRow({ id: 'z2', name: 'Terrace' })];

async function form(table: TableOut | null, more: Record<string, unknown> = {}, answers: Record<string, [number, unknown]> = {}) {
  const m = await mountTable(TableFormModal, { props: { open: false, table, zones: ZONES, canDelete: true, ...more }, answers });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`table-form-${name}`) as Control;
  return { ...m, field, closed: () => m.wrapper.props('open') === false };
}

describe('TableFormModal · edit', () => {
  it('a live repaint of the same table keeps what is being typed; another table starts over', async () => {
    // Edit plan is live: another device moving or seating this table sends a new row with the same id.
    const f = await form(tableRow({ name: 'Window' }));
    await ionValue(f.field('capacity'), '6', 'ionInput');
    await f.wrapper.setProps({ table: tableRow({ name: 'Window', position_x: 300 }) });
    await settle();
    expect(f.field('capacity').value).toBe('6');
    await f.wrapper.setProps({ table: tableRow({ id: 't9', number: '9', name: '' }) });
    await settle();
    expect([f.field('number').value, f.field('capacity').value]).toEqual(['9', '4']);
  });

  it('shows the table with the old labels and sends only what changed', async () => {
    const f = await form(tableRow({ name: 'Window' }), {}, { '/api/table/tables/update': [200, tableRow()] });
    expect(f.inDoc('table-form')?.getAttribute('aria-label')).toBe('Edit table');
    expect([f.field('number').label, f.field('capacity').label, f.field('name').label, f.field('shape').label, f.field('status').label, f.field('zone').label]).toEqual([
      'Number',
      'Capacity',
      'Name (optional)',
      'Shape',
      'Status',
      'Zone',
    ]);
    expect([f.field('number').value, f.field('capacity').value, f.field('name').value, f.field('status').value]).toEqual(['4', '4', 'Window', 'available']);
    await ionValue(f.field('capacity'), '6', 'ionInput');
    await ionValue(f.field('status'), 'blocked');
    await ionValue(f.field('zone'), 'z2');
    await click(f.field('submit'));
    expect(f.sent()).toEqual([
      { method: 'POST', path: '/api/table/tables/update', query: {}, body: { id: 't1', capacity: 6, blocked: true, move_to_zone_id: 'z2' } },
    ]);
    expect(f.closed()).toBe(true);
  });

  it('a number is required and a taken one is refused in the dialog', async () => {
    const taken = { error: { code: 'table.number_taken', message: 'There is already a table with that number in this zone.' } };
    const f = await form(tableRow(), {}, { '/api/table/tables/update': [409, taken] });
    await ionValue(f.field('number'), ' ', 'ionInput');
    expect(f.field('submit').disabled).toBe(true);
    expect(f.field('number-required').textContent).toContain('The table number is required');
    await ionValue(f.field('number'), '5', 'ionInput');
    await click(f.field('submit'));
    expect(f.field('error').textContent).toContain('There is already a table with that number in this zone.');
    expect(f.closed()).toBe(false);
  });

  it('takes a table out of use', async () => {
    const f = await form(tableRow(), {}, { '/api/table/tables/update': [200, tableRow()] });
    await ionChecked(f.field('active'), false);
    await click(f.field('submit'));
    expect(f.sent().map((call) => call.body)).toEqual([{ id: 't1', is_active: false }]);
  });

  it('deletes after asking, and only whoever may', async () => {
    const f = await form(tableRow(), {}, { '/api/table/tables/delete': [200, { id: 't1' }] });
    await click(f.field('delete'));
    expect(f.inDoc('table-form-delete-confirm')?.textContent).toContain('It leaves the plan and the lists; its history of checks stays.');
    await click(f.inDoc('table-form-delete-confirm-submit'));
    expect(f.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/tables/delete', { id: 't1' }]]);
    expect(f.closed()).toBe(true);
    const nobody = await form(tableRow(), { canDelete: false });
    expect(nobody.field('delete')).toBeNull();
  });
});

describe('TableFormModal · new', () => {
  it('asks Number, Capacity and Zone, and an empty number is numbered by the server', async () => {
    const f = await form(null, { defaultZoneId: 'z2' }, { '/api/table/tables': [201, tableRow()] });
    expect(f.inDoc('table-form')?.getAttribute('aria-label')).toBe('New table');
    expect(f.field('name')).toBeNull();
    expect(f.field('zone').value).toBe('z2');
    await ionValue(f.field('capacity'), '2', 'ionInput');
    await click(f.field('submit'));
    expect(f.sent()).toEqual([{ method: 'POST', path: '/api/table/tables', query: {}, body: { zone_id: 'z2', capacity: 2 } }]);
    expect(f.closed()).toBe(true);
  });
});

// «Edit table» and «New table» (WORKBOOK «Plano de sala», «Mesas»; TABLE-F02, F04, F05): Number,
// Capacity, Width and Height of its box on the plan, Name (optional), Shape, Status (Available or Blocked:
// the others are the room's, not a person's), Zone and In use; «Save» sends only what changed, a new size
// as a move of the box where it is; «Delete» (whoever may) asks first. A new table asks Number (empty = the
// first free one), Capacity, Width and Height (empty = the standard box) and Zone. Refusals stay in the dialog.
import { describe, expect, it } from 'vitest';

import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import { click, ionChecked, ionValue, mountTable, settle } from '../__tests__/mount-table';
import { tableRow, zoneRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import TableFormModal from './TableFormModal.vue';

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; disabled?: boolean };

const ZONES = [zoneRow(), zoneRow({ id: 'z2', name: 'Terrace' })];

/** A field as Ionic Vue leaves it: its limits, its hint and the words under it are the element's properties. */
type Field = Control & { min?: unknown; max?: unknown; placeholder?: string; errorText?: string };

async function form(table: TableOut | null, more: Record<string, unknown> = {}, answers: Record<string, [number, unknown]> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(TableFormModal, { props: { open: false, table, zones: ZONES, canDelete: true, ...more }, answers, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`table-form-${name}`) as Field;
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

  it('shows its box on the plan as Width and Height, within the server’s limits; a new size moves the box where it is', async () => {
    const f = await form(tableRow({ width: 72, height: 72 }), {}, { '/api/table/tables/move': [200, tableRow()] });
    expect([f.field('width').label, f.field('height').label, f.field('width').value, f.field('height').value]).toEqual(['Width', 'Height', '72', '72']);
    expect(['width', 'height'].map((name) => [String(f.field(name).min), String(f.field(name).max)])).toEqual([
      ['24', '10000'],
      ['24', '10000'],
    ]);
    await ionValue(f.field('width'), '160', 'ionInput');
    await click(f.field('submit'));
    expect(f.sent()).toEqual([
      { method: 'POST', path: '/api/table/tables/move', query: {}, body: { id: 't1', position_x: 16, position_y: 16, width: 160 } },
    ]);
    expect(f.closed()).toBe(true);
  });

  it('a new size with other changes moves the box first and then saves the rest', async () => {
    const f = await form(tableRow(), {}, { '/api/table/tables/move': [200, tableRow()], '/api/table/tables/update': [200, tableRow()] });
    await ionValue(f.field('capacity'), '8', 'ionInput');
    await ionValue(f.field('height'), '120', 'ionInput');
    await click(f.field('submit'));
    expect(f.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/table/tables/move', { id: 't1', position_x: 16, position_y: 16, height: 120 }],
      ['/api/table/tables/update', { id: 't1', capacity: 8 }],
    ]);
    expect(f.closed()).toBe(true);
  });

  it('an emptied side keeps the size the table has', async () => {
    const f = await form(tableRow(), {}, { '/api/table/tables/update': [200, tableRow()] });
    await ionValue(f.field('width'), '', 'ionInput');
    await ionValue(f.field('capacity'), '8', 'ionInput');
    await click(f.field('submit'));
    expect(f.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/tables/update', { id: 't1', capacity: 8 }]]);
  });

  it('a size the server refuses is said under its field, and nothing else is saved', async () => {
    const refused = { error: { code: 'invalid_payload', message: 'Check the highlighted details.', fields: { width: 'Ensure this value is greater than or equal to 24.' } } };
    const f = await form(tableRow(), {}, { '/api/table/tables/move': [422, refused] });
    await ionValue(f.field('capacity'), '8', 'ionInput');
    await ionValue(f.field('width'), '10', 'ionInput');
    await click(f.field('submit'));
    expect(f.sent().map((call) => call.path)).toEqual(['/api/table/tables/move']);
    expect(f.field('width').errorText).toBe('Ensure this value is greater than or equal to 24.');
    expect(f.field('width').classList.contains('ion-invalid')).toBe(true);
    expect(f.closed()).toBe(false);
  });

  it('once the refused size is emptied, what the rest is refused with is said instead', async () => {
    const refused = { error: { code: 'invalid_payload', message: 'Check the highlighted details.', fields: { width: 'Ensure this value is greater than or equal to 24.' } } };
    const taken = { error: { code: 'table.number_taken', message: 'There is already a table with that number in this zone.' } };
    const f = await form(tableRow(), {}, { '/api/table/tables/move': [422, refused], '/api/table/tables/update': [409, taken] });
    await ionValue(f.field('width'), '10', 'ionInput');
    await click(f.field('submit'));
    await ionValue(f.field('width'), '', 'ionInput');
    await ionValue(f.field('number'), '5', 'ionInput');
    await click(f.field('submit'));
    expect(f.sent().map((call) => call.path)).toEqual(['/api/table/tables/move', '/api/table/tables/update']);
    expect(f.field('error').textContent).toContain('There is already a table with that number in this zone.');
    expect(f.field('width').errorText ?? '').toBe('');
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

  it('asks Width and Height too: empty is the standard box, a long table is created with its size', async () => {
    const f = await form(null, { defaultZoneId: 'z2' }, { '/api/table/tables': [201, tableRow()] }, 'es');
    expect(['width', 'height'].map((name) => [f.field(name).label, f.field(name).value, f.field(name).placeholder])).toEqual([
      ['Ancho', '', 'Estándar'],
      ['Alto', '', 'Estándar'],
    ]);
    await ionValue(f.field('width'), '160', 'ionInput');
    await ionValue(f.field('height'), '72', 'ionInput');
    await click(f.field('submit'));
    expect(f.sent().map((call) => call.body)).toEqual([{ zone_id: 'z2', capacity: 4, width: 160, height: 72 }]);
  });
});

describe('TableFormModal: a size refused with the same words', () => {
  itTellsTheCorrectedFieldApart(['width', 'height'], async (locale, refusal) => {
    const f = await form(tableRow(), {}, { '/api/table/tables/move': [422, refusal] }, locale);
    await ionValue(f.field('width'), '10', 'ionInput');
    await ionValue(f.field('height'), '10', 'ionInput');
    return { field: f.field, send: () => click(f.field('submit')), settle };
  }, 'width');
});

describe('TableFormModal: fields refused with the same words (hub#888)', () => {
  // Editing shows the three fields that paint a refusal (a new table has no Name); each is refused under its own key.
  itTellsTheCorrectedFieldApart(['number', 'capacity', 'name'], async (locale, refusal) => {
    const f = await form(tableRow({ name: 'Window' }), {}, { '/api/table/tables/update': [422, refusal] }, locale);
    await ionValue(f.field('capacity'), '6', 'ionInput');
    return { field: f.field, send: () => click(f.field('submit')), settle };
  }, 'capacity');
});

describe('TableFormModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const f = await form(null);
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => f.inDoc('table-form'),
      change: () => ionValue(f.field('number'), '7', 'ionInput'),
      restore: () => ionValue(f.field('number'), '', 'ionInput'),
    });
  });
});

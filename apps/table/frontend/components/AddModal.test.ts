// The plan's «+» (WORKBOOK «Plano de sala»; TABLE-F01, F02): «Add», with Zone («New zone…») and «Add zone»
// — the new zone goes last and becomes the chosen one —, and «Table number» («Auto-numbered» when left
// empty) with «Add table», off while there is no zone. Each action owns its field; a refusal stays here.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountTable, settle } from '../__tests__/mount-table';
import { tableRow, zoneRow } from '../__tests__/tables';
import AddModal from './AddModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { placeholder?: string; disabled?: boolean };

async function add(zoneId: string | null, answers: Record<string, [number, unknown]> = {}) {
  const m = await mountTable(AddModal, { props: { open: false, zoneId }, answers });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`table-add-${name}`) as Control;
  return { ...m, field, closed: () => m.wrapper.props('open') === false };
}

describe('AddModal', () => {
  it('adds a zone, which becomes the chosen one', async () => {
    const a = await add(null, { '/api/table/zones': [201, zoneRow({ id: 'z7', name: 'Terrace' })] });
    expect(a.inDoc('table-add')?.getAttribute('aria-label')).toBe('Add');
    expect(a.field('zone-submit').disabled).toBe(true);
    await ionValue(a.field('zone-name'), 'Terrace', 'ionInput');
    await click(a.field('zone-submit'));
    expect(a.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/zones', { name: 'Terrace' }]]);
    expect(a.wrapper.emitted('zone')?.[0]).toEqual(['z7']);
    expect(a.closed()).toBe(true);
  });

  it('adds a table to the chosen zone, numbered by the server when left empty, and is off without a zone', async () => {
    const off = await add(null);
    expect(off.field('table-submit').disabled).toBe(true);
    const a = await add('z1', { '/api/table/tables': [201, tableRow()] });
    expect(a.field('table-number').placeholder).toBe('Auto-numbered');
    await click(a.field('table-submit'));
    expect(a.sent().map((call) => call.body)).toEqual([{ zone_id: 'z1' }]);
    expect(a.closed()).toBe(true);
    const named = await add('z1', { '/api/table/tables': [201, tableRow()] });
    await ionValue(named.field('table-number'), 'T1', 'ionInput');
    await click(named.field('table-submit'));
    expect(named.sent().map((call) => call.body)).toEqual([{ zone_id: 'z1', number: 'T1' }]);
  });

  it('a number taken in the zone is refused here', async () => {
    const taken = { error: { code: 'table.number_taken', message: 'There is already a table with that number in this zone.' } };
    const a = await add('z1', { '/api/table/tables': [409, taken] });
    await ionValue(a.field('table-number'), '1', 'ionInput');
    await click(a.field('table-submit'));
    expect(a.field('error').textContent).toContain('There is already a table with that number in this zone.');
    expect(a.closed()).toBe(false);
  });
});

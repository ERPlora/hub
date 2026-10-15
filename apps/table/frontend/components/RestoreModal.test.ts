// «Seat again» a parked check (WORKBOOK «Sesiones»; TABLE-F24): the tables free right now (available or
// reserved, in service), live, to pick one; «Seat» seats it there. With none free, it says so.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountTable, page, settle } from '../__tests__/mount-table';
import { occupied, sessionRow, tableRow } from '../__tests__/tables';
import RestoreModal from './RestoreModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'table.table.list';
type Control = HTMLElement & { value?: unknown; disabled?: boolean };

async function restore(answers: Record<string, [number, unknown]> = {}) {
  const parked = sessionRow({ id: 's9', status: 'parked', table_id: null, table_number: null });
  const m = await mountTable(RestoreModal, { props: { open: true, session: parked }, answers });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.live();
  const field = (name: string) => m.inDoc(`table-restore-${name}`) as Control;
  return { ...m, field, closed: () => m.wrapper.props('open') === false };
}

describe('RestoreModal', () => {
  it('offers the free tables in service and seats the check at the one picked', async () => {
    const r = await restore({ '/api/table/sessions/restore': [200, sessionRow()] });
    expect(r.params(OP)).toEqual([{ in_service: true, sort: 'number', limit: 100 }]);
    const free = tableRow({ id: 't6', number: '6', zone_name: 'Terrace' });
    const reserved = tableRow({ id: 't7', number: '7', status: 'reserved' });
    await r.result(OP, page([free, reserved, occupied({ id: 't8', number: '8' })], 3, 100));
    await settle();
    const options = [...r.field('table').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim());
    expect(options).toEqual(['6 · Terrace', '7 · Dining room']);
    expect(r.field('submit').disabled).toBe(true);
    await ionValue(r.field('table'), 't6');
    await click(r.field('submit'));
    expect(r.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/sessions/restore', { id: 's9', table_id: 't6' }]]);
    expect(r.closed()).toBe(true);
  });

  it('with no free table, says so', async () => {
    const r = await restore();
    await r.result(OP, page([occupied()], 1, 100));
    await settle();
    expect(r.field('none').textContent).toContain('No free table right now.');
  });
});

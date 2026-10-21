// Tables → Sessions (WORKBOOK «Pantallas · Sesiones»; TABLE-F21 to F24): the checks of the room, «Open»,
// «Closed» and «All». Table («No table (parked)»), Charged and Closed (not in Open), Zone, Server,
// Guests, Opened, Time (amber and red after the room settings, an open check only) and Status; «Search
// table…», filters by zone, server and status; newest first. Details, Close session (asks first; Sales’
// refusal shows), Seat again (a parked one) and Delete (a finished one, owner and admin).
import { ConfirmDialog, DataTable } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, flush, type MountOptions, mountTable, page } from '../__tests__/mount-table';
import { NOW, sessionRow, SETTINGS, zoneRow } from '../__tests__/tables';
import RestoreModal from '../components/RestoreModal.vue';
import SessionDetailModal from '../components/SessionDetailModal.vue';
import SessionsPage from './SessionsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'table.session.list';
const OPEN = sessionRow({ id: 's1', opened_at: '2026-10-14T18:30:00Z' }); // 70 min: amber
const LATE = sessionRow({ id: 's2', table_number: '7', opened_at: '2026-10-14T18:00:00Z' }); // 100 min: red
const CLOSED = sessionRow({ id: 's3', status: 'closed', closed_at: '2026-10-14T19:00:00Z', paid_total: 4250 });
const PARKED = sessionRow({ id: 's4', status: 'parked', table_id: null, table_number: null, zone_name: null });

async function setup(options: MountOptions = {}) {
  const m = await mountTable(SessionsPage, { path: '/table/sessions', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="table-sessions-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const columns = () => prop<Array<{ key: string; label: string }>>('columns').map((c) => c.key);
  const show = async (rows: unknown[]) => {
    await m.result('table.settings.get', SETTINGS);
    await m.result('table.zone.list', page([zoneRow()]));
    await m.result('table.waiter.list', page([{ id: '2', name: 'Luis' }]));
    await m.result(OP, page(rows));
  };
  const segment = async (value: string) => {
    const el = m.wrapper.find('[data-testid="table-sessions-segment"]').element;
    el.dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true }));
    await flush();
  };
  const action = (actionId: string, row: unknown) => {
    table().vm.$emit('action', { actionId, row });
    return flush();
  };
  const dialog = (testid: string) => m.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === testid);
  return { ...m, table, prop, rows, cells, columns, show, segment, action, dialog, list: () => m.params(OP) };
}

describe('SessionsPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it('starts on the open checks, newest first, with their time in amber and red', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.list()).toEqual([{ status: 'open', sort: '-opened_at', limit: 50, offset: 0 }]);
    await s.show([OPEN, LATE]);
    expect(s.columns()).toEqual(['table_number', 'zone_name', 'waiter_name', 'guests_count', 'opened_at', 'duration', 'status']);
    expect(s.cells(0).slice(0, 7)).toEqual(['4', 'Dining room', 'Luis', '3 pax', '20:30', '70 min', 'Abierta']);
    expect(s.rows()[0].find('[data-tone]').attributes('data-tone')).toBe('warning');
    expect(s.rows()[1].find('[data-tone]').attributes('data-tone')).toBe('critical');
  });

  it('«Closed» shows what was charged and when; «All» every check, a parked one without table', async () => {
    const s = await setup();
    await s.show([OPEN]);
    await s.segment('closed');
    expect(s.list()).toEqual([{ status: 'closed', sort: '-opened_at', limit: 50, offset: 0 }]);
    await s.result(OP, page([CLOSED]));
    expect(s.columns()).toEqual(['table_number', 'paid_total', 'closed_at', 'zone_name', 'waiter_name', 'guests_count', 'opened_at', 'duration', 'status']);
    expect(s.cells(0).slice(0, 3)).toEqual(['4', '€42.50', '9:00 PM']);
    await s.segment('all');
    expect(s.list()).toEqual([{ sort: '-opened_at', limit: 50, offset: 0 }]);
    await s.result(OP, page([PARKED]));
    expect(s.cells(0)[0]).toBe('No table (parked)');
  });

  it('searches the table and filters by zone, server and status on the server', async () => {
    const s = await setup();
    await s.show([OPEN]);
    // The filters wait behind the table's funnel, as in the old list: open on a phone they took the screen.
    expect(s.prop('filterable')).toBe(true);
    s.table().vm.$emit('update:search', '4');
    s.table().vm.$emit('filtersChange', { zone_id: 'z1', waiter_id: '2' });
    await flush();
    expect(s.list()).toEqual([{ search: '4', status: 'open', zone_id: 'z1', waiter_id: '2', sort: '-opened_at', limit: 50, offset: 0 }]);
  });

  it('closes an open check after asking, and Sales’ refusal shows in the dialog', async () => {
    const s = await setup();
    await s.show([OPEN]);
    expect(s.prop<Array<{ id: string; hidden?: (row: unknown) => boolean }>>('actions').map((a) => [a.id, a.hidden?.(OPEN) ?? false])).toEqual([
      ['detail', false],
      ['close', false],
      ['restore', true],
      ['delete', true],
    ]);
    await s.action('close', OPEN);
    const dialog = s.dialog('table-sessions-close');
    expect([dialog?.props('title'), dialog?.props('message')]).toEqual([
      'Close the session?',
      'Table 4 · 3 guests. The table is freed and the session moves to the history. If its bill is still open in Sales, first charge it, move it to another table or delete it from the till.',
    ]);
    s.answer(409, { error: { code: 'table.session_bill_open', message: 'This table’s bill is still open in Sales.' } });
    dialog?.vm.$emit('confirm');
    await flush();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/sessions/close', { id: 's1', order_id: 'o1' }]]);
    expect(s.dialog('table-sessions-close')?.props('error')).toMatchObject({ message: 'This table’s bill is still open in Sales.' });
  });

  it('Details, Seat again and Delete open their dialogs', async () => {
    const s = await setup();
    await s.show([CLOSED, PARKED]);
    await s.action('detail', CLOSED);
    expect(s.wrapper.findComponent(SessionDetailModal).props('session')).toEqual(CLOSED);
    await s.action('restore', PARKED);
    expect(s.wrapper.findComponent(RestoreModal).props('session')).toEqual(PARKED);
    await s.action('delete', CLOSED);
    const dialog = s.dialog('table-sessions-delete');
    expect(dialog?.props('title')).toBe('Delete this check from the history?');
    s.answer(200, { id: 's3' });
    dialog?.vm.$emit('confirm');
    await flush();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/sessions/delete', { id: 's3' }]]);
  });

  it('a waiter closes and seats again, but does not delete', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show([OPEN]);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['detail', 'close', 'restore']);
  });
});

describe('SessionsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});

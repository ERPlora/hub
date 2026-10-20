// «Your automations» (WORKBOOK FLOW-F02, F03, F06, F07): the live list of the business's automations in a
// server-side DataTable — name and when it starts in words, its last run, Active/Paused with its switch
// —, search, «Showing», «Starts with» and «Order»; several chosen are turned on or paused at once; each
// row is copied or deleted (asked first); a row opens the editor.
import { DataTable } from '@erplora/ui/components';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { CatalogOut, FlowOut } from '../operations';
import { click, flush, ionChecked, ionValue, mountFlow, page, settle } from '../__tests__/mount-flow';
import FlowList from './FlowList.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), toastSuccess: vi.fn(async () => undefined), toastInfo: vi.fn(async () => undefined) }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: mocks.toastSuccess,
  toastInfo: mocks.toastInfo,
}));
afterEach(() => {
  mocks.confirm.mockReset();
  mocks.toastSuccess.mockClear();
  mocks.toastInfo.mockClear();
});

const OP = 'flow.flow.list';
const CATALOG = { events: [{ name: 'sale.sale.completed', app: 'sale', app_name: 'Sales' }], actions: [] } as unknown as CatalogOut;

const flow = (id: string, over: Partial<FlowOut> = {}): FlowOut =>
  ({
    id,
    name: `Flow ${id}`,
    enabled: true,
    trigger: { kind: 'event', event: 'sale.sale.completed' },
    steps: [],
    grants: [],
    required_grants: [],
    missing_grants: [],
    version: 1,
    next_fire_at: null,
    created_at: '2026-10-15T10:00:00+02:00',
    updated_at: '2026-10-15T10:00:00+02:00',
    created_by: '',
    updated_by: '',
    last_run: null,
    ...over,
  }) as FlowOut;

async function setup(rows: FlowOut[] = [flow('f1'), flow('f2', { enabled: false, name: 'Weekly', trigger: { kind: 'schedule', every: 'day', time: '09:00' }, last_run: { id: 'r1', status: 'failed', started_at: '2026-10-15T09:00:00+02:00' } })], answers: Record<string, [number, unknown]> = {}) {
  const m = await mountFlow(FlowList, { props: { catalog: CATALOG, allTotal: rows.length }, answers });
  await m.live();
  await m.result(OP, page(rows, rows.length));
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const rowsShown = () => m.wrapper.findAll('[data-testid="flow-list-row"]');
  return { ...m, table, rowsShown };
}

describe('FlowList', () => {
  it('says once when its first page is painted, so a link can bring a card below into view (FLOW-F05)', async () => {
    const m = await mountFlow(FlowList, { props: { catalog: CATALOG, allTotal: 1 } });
    await m.live();
    expect(m.wrapper.emitted('ready')).toBeUndefined();
    await m.result(OP, page([flow('f1')], 1));
    await m.result(OP, page([flow('f1'), flow('f2')], 2));
    expect(m.wrapper.emitted('ready')).toHaveLength(1);
  });

  it('follows the list live, the last touched first, 50 a page', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: '-updated_at', limit: 50, offset: 0 }]);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, selectable: true, testid: 'flow-list', total: 2 });
    expect((s.table().props() as Record<string, unknown>).searchPlaceholder).toBe('Search by name, by what starts it or by what it does');
  });

  it('each row says its name, when it starts, its last run and whether it is on', async () => {
    const s = await setup();
    const [first, second] = s.rowsShown();
    expect(first.text()).toContain('Flow f1');
    expect(first.text()).toContain('When a sale is charged');
    expect(first.text()).toContain('Never ran');
    expect(first.text()).toContain('Active');
    expect(second.text()).toContain('Every day at 09:00');
    expect(second.text()).toContain('Stopped by an error');
    expect(second.text()).toContain('Paused');
  });

  it('«Showing», «Starts with» and «Order» query the server again', async () => {
    const s = await setup();
    await ionValue(s.find('flow-list-state').element, 'paused');
    await ionValue(s.find('flow-list-trigger').element, 'schedule');
    await ionValue(s.find('flow-list-sort').element, 'name');
    await s.reopen();
    expect(s.params(OP)).toEqual([{ sort: 'name', enabled: false, trigger_kind: 'schedule', limit: 50, offset: 0 }]);
    expect(s.find('flow-list-count').text()).toBe('Showing 2 of 2');
  });

  it('the switch turns one on, and warns when it lacks its permissions', async () => {
    const s = await setup(undefined, { '/api/flow/flows/set_enabled': [200, flow('f2', { enabled: true, missing_grants: ['task.task.create'] })] });
    await ionChecked(s.find('flow-list-toggle-f2').element, true);
    await settle();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/flow/flows/set_enabled', { id: 'f2', enabled: true }]]);
    expect(mocks.toastInfo).toHaveBeenCalledWith(
      'On, but it still lacks the permissions it asks for: it will do nothing until you allow them in its Permissions tab.',
    );
  });

  it('several chosen are turned on or paused, one after another', async () => {
    const s = await setup(undefined, { '/api/flow/flows/set_enabled': [200, flow('f1', { enabled: false })] });
    s.table().vm.$emit('update:selected', ['f1', 'f2']);
    await flush();
    await click(s.find('flow-list-bulk-pause').element);
    await settle();
    expect(s.sent().map((call) => call.body)).toEqual([
      { id: 'f1', enabled: false },
      { id: 'f2', enabled: false },
    ]);
    expect((s.table().props() as Record<string, unknown>).selected).toEqual([]);
  });

  it('a copy says it is paused and has no permissions; deleting asks first', async () => {
    const s = await setup(undefined, {
      '/api/flow/flows/duplicate': [201, flow('f3')],
      '/api/flow/flows/delete': [200, { id: 'f1' }],
    });
    s.table().vm.$emit('action', { actionId: 'duplicate', row: flow('f1') });
    await settle();
    expect(mocks.toastSuccess).toHaveBeenCalledWith(
      "Copied, and the copy is paused. It has none of the original's permissions: allow what it needs before turning it on.",
    );
    mocks.confirm.mockResolvedValue(false);
    s.table().vm.$emit('action', { actionId: 'delete', row: flow('f1') });
    await settle();
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Delete «Flow f1»?',
      message: 'This cannot be undone. Its history stays.',
      tone: 'danger',
      confirmLabel: 'Yes, delete it',
      cancelLabel: 'Leave it',
    });
    expect(s.sent().map((call) => call.path)).toEqual(['/api/flow/flows/duplicate']);
    mocks.confirm.mockResolvedValue(true);
    s.table().vm.$emit('action', { actionId: 'delete', row: flow('f1') });
    await settle();
    expect(s.sent().map((call) => call.path)).toEqual(['/api/flow/flows/duplicate', '/api/flow/flows/delete']);
  });

  it('a row opens the editor', async () => {
    const s = await setup();
    s.table().vm.$emit('rowClick', flow('f1'));
    expect(s.wrapper.emitted('open')).toEqual([[flow('f1')]]);
  });

  it('a refusal is said above the list', async () => {
    const s = await setup(undefined, { '/api/flow/flows/set_enabled': [404, { error: { code: 'not_found', message: 'That automation does not exist in this business.' } }] });
    await ionChecked(s.find('flow-list-toggle-f1').element, false);
    await settle();
    expect(s.find('flow-list-error').text()).toContain('That automation does not exist in this business.');
  });

  it('a search that finds nothing offers to show them all again', async () => {
    const s = await setup();
    s.table().vm.$emit('update:search', 'zzz');
    await flush();
    await s.reopen();
    await s.result(OP, page([], 0));
    expect(s.find('flow-list-nomatch').text()).toContain('Nothing here matches that.');
    await click(s.find('flow-list-clear').element);
    await s.reopen();
    expect(s.params(OP)).toEqual([{ sort: '-updated_at', limit: 50, offset: 0 }]);
  });
});

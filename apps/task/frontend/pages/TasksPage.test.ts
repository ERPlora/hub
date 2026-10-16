// Tasks → Tasks (WORKBOOK «Pantallas · Tareas»; TASK-F01 to F07): «All» follows the live
// `task.task.list` in a server-side DataTable — No., Title, Status, Priority (a coloured chip), Due (red
// «Overdue», amber «Due today»), Assignee and Project (hidden) —, the newest first, «Search no. or
// title…», column filters, list or cards, 50 a page. «My tasks» (only with a staff record) follows
// `task.task.mine`, and a task completed from its card stays in its slot as done. A row offers Detail,
// Start and Complete where they apply; the row and Detail open the sheet; «+» opens «New task».
import { DataTable, EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { TaskOut } from '../operations';
import { EMPLOYEE, flush, ionValue, mountTask, type MountOptions, page } from '../__tests__/mount-task';
import { task } from '../__tests__/task';
import TaskFormModal from '../components/TaskFormModal.vue';
import TaskSheet from '../components/TaskSheet.vue';
import TasksPage from './TasksPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
const toastSuccess = vi.hoisted(() => vi.fn<(message: string) => Promise<void>>(async () => undefined));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({ ...(await importOriginal<typeof import('@erplora/ui/shell')>()), toastSuccess }));

const ALL = 'task.task.list';
const MINE = 'task.task.mine';
const ME = 'staff.member.mine';
const ROWS = [
  task({ id: 't1', priority: 'urgent', due_date: '2020-01-01', status: 'todo', assignee_name: 'Ana López' }),
  task({ id: 't2', number: 'TSK-20261015-0002', title: 'Order dye', status: 'in_progress', priority: 'low' }),
  task({ id: 't3', number: 'TSK-20261015-0003', title: 'Fix the sign', status: 'done', completed_at: '2026-10-15T09:00:00Z', due_date: '2020-01-01' }),
];

async function setup(options: MountOptions & { me?: unknown } = {}) {
  const m = await mountTask(TasksPage, { path: '/task/tasks', ...options });
  await m.live();
  if (options.me !== null) await m.result(ME, options.me ?? { member: { id: 'm9' } });
  const tables = () => m.wrapper.findAllComponents(DataTable as unknown as Component);
  const table = () => tables()[0];
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="task-tasks-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const actions = (row: TaskOut) =>
    prop<Array<{ id: string; hidden?: (r: TaskOut) => boolean }>>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => a.id);
  return { ...m, table, prop, rows, cells, actions, show: (data: unknown, op: typeof ALL | typeof MINE = ALL) => m.result(op, data) };
}

describe('TasksPage · All', () => {
  it('follows every task, the newest first, 50 from the first', async () => {
    const s = await setup();
    expect(s.params(ALL)).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'task-tasks', total: 3, views: ['table', 'cards'] });
    expect(s.prop('searchPlaceholder')).toBe('Search no. or title…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New task');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Tasks');
  });

  it('paints No., Title, Status, Priority as a chip, Due with its warning, and Assignee; Project hidden', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string; hidden?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.hidden])).toEqual([
      ['number', 'No.', false],
      ['title', 'Title', false],
      ['status', 'Status', false],
      ['priority', 'Priority', false],
      ['due_date', 'Due', false],
      ['assignee_name', 'Assignee', false],
      ['project_name', 'Project', true],
    ]);
    expect(s.cells(0).slice(0, 6)).toEqual(['TSK-20261015-0001', 'Clean the store room', 'To Do', 'Urgent', '01/01/2020', 'Ana López']);
    expect(s.cells(1)[4]).toBe('—');
    const due = s.rows()[0].find('[data-testid="task-due"]');
    expect(due.attributes('aria-label')).toBe('Overdue');
    // A task already done is never painted as late.
    expect(s.rows()[2].find('[data-testid="task-due"]').attributes('aria-label')).toBeUndefined();
    const chip = s.rows()[0].findAllComponents(StatusPill).map((p: { props: (key: string) => unknown }) => [p.props('label'), p.props('tone')]);
    expect(chip).toEqual([
      ['To Do', 'neutral'],
      ['Urgent', 'danger'],
    ]);
  });

  it('filters by column: status and priority from their lists, the due day, the assignee and the project', async () => {
    const s = await setup();
    await s.result('task.project.list', page([{ id: 'p1', name: 'Opening' }]));
    const columns = s.prop<Array<{ key: string; filter?: { type: string; key?: string; options?: Array<{ value: string; label: string }> } }>>('columns');
    expect(columns.find((c) => c.key === 'status')?.filter?.options?.map((o) => o.label)).toEqual(['To Do', 'In Progress', 'Blocked', 'Done', 'Cancelled']);
    expect(columns.find((c) => c.key === 'project_name')?.filter).toEqual({ type: 'select', key: 'project_id', options: [{ value: 'p1', label: 'Opening' }] });
    s.table().vm.$emit('filtersChange', { number: '0042', status: 'blocked', priority: 'high', due_date: '2026-10-20', assignee_name: 'ana', project_id: 'p1' });
    await flush();
    expect(s.params(ALL)).toEqual([
      {
        number: '0042',
        status: 'blocked',
        priority: 'high',
        due_from: '2026-10-20',
        due_to: '2026-10-20',
        assignee: 'ana',
        project_id: 'p1',
        sort: '-created_at',
        limit: 50,
        offset: 0,
      },
    ]);
  });

  it('sorts and searches on the server; no task at all says «No tasks.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No tasks.');
    s.table().vm.$emit('sortChange', { sort: 'priority', dir: 'desc' });
    s.table().vm.$emit('update:search', 'store');
    await flush();
    expect(s.params(ALL)).toEqual([{ search: 'store', sort: '-priority', limit: 50, offset: 0 }]);
  });

  it('offers Start and Complete only where they apply, and only on a task the caller may change', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.actions(ROWS[0])).toEqual(['detail', 'start', 'complete']);
    expect(s.actions(ROWS[1])).toEqual(['detail', 'complete']);
    expect(s.actions(ROWS[2])).toEqual(['detail']);
    expect(s.actions({ ...ROWS[0], can_change: false })).toEqual(['detail']);
  });

  it('Start and Complete say they worked; a refusal is said above the table', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, ROWS[0]);
    s.table().vm.$emit('action', { actionId: 'start', row: ROWS[0] });
    await flush();
    s.table().vm.$emit('action', { actionId: 'complete', row: ROWS[1] });
    await flush();
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([
      ['/api/task/tasks/set_status', { id: 't1', status: 'in_progress' }],
      ['/api/task/tasks/complete', { id: 't2' }],
    ]);
    expect(toastSuccess.mock.calls.map(([message]) => message)).toEqual(['Task started', 'Task completed']);
    s.answer(409, { error: { code: 'task.task_already_closed', message: 'That task is already closed, so it was left as it was.' } });
    s.table().vm.$emit('action', { actionId: 'complete', row: ROWS[0] });
    await flush();
    await flush();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'task-tasks-row-error');
    expect(banner?.text()).toContain('That task is already closed, so it was left as it was.');
  });

  it('the row and Detail open the task’s sheet; «+» opens «New task»', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(TaskSheet).exists()).toBe(false);
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect(s.wrapper.findComponent(TaskSheet).props()).toMatchObject({ open: true, taskId: 't2' });
    s.table().vm.$emit('add');
    await flush();
    expect([s.wrapper.findComponent(TaskFormModal).props('open'), s.wrapper.findComponent(TaskFormModal).props('task')]).toEqual([true, null]);
  });

  it('an employee without the add permission has no «+»', async () => {
    const s = await setup({ session: { ...EMPLOYEE, permissions: ['task.view'] } });
    expect(s.prop('addable')).toBe(false);
  });
});

describe('TasksPage · My tasks', () => {
  it('is offered only to whoever has a staff record', async () => {
    const s = await setup({ me: { member: null } });
    expect(s.wrapper.find('[data-testid="task-view-mine"]').exists()).toBe(false);
    const withRecord = await setup();
    expect(withRecord.wrapper.find('[data-testid="task-view-mine"]').exists()).toBe(true);
  });

  it('follows my open tasks and keeps the one I complete in its slot, as done, until I leave the tab', async () => {
    const s = await setup();
    await ionValue(s.wrapper.find('[data-testid="task-views"]').element, 'mine', 'ionChange');
    expect(s.params(MINE)).toEqual([{ limit: 50, offset: 0 }]);
    const mine = [ROWS[0], ROWS[1]];
    await s.show(page(mine), MINE);
    expect(s.prop('testid')).toBe('task-mine');
    s.answer(200, { ...ROWS[0], status: 'done' });
    s.table().vm.$emit('action', { actionId: 'complete', row: ROWS[0] });
    await flush();
    await s.show(page([ROWS[1]]), MINE);
    expect(s.prop<TaskOut[]>('rows').map((r) => [r.id, r.status])).toEqual([
      ['t1', 'done'],
      ['t2', 'in_progress'],
    ]);
    await ionValue(s.wrapper.find('[data-testid="task-views"]').element, 'all', 'ionChange');
    await ionValue(s.wrapper.find('[data-testid="task-views"]').element, 'mine', 'ionChange');
    await s.show(page([ROWS[1]]), MINE);
    expect(s.prop<TaskOut[]>('rows').map((r) => r.id)).toEqual(['t2']);
  });

  it('with nothing assigned says so', async () => {
    const s = await setup();
    await ionValue(s.wrapper.find('[data-testid="task-views"]').element, 'mine', 'ionChange');
    await s.show(page([]), MINE);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No open tasks assigned to you.');
  });
});

describe('TasksPage · Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.cells(0).slice(2, 4)).toEqual(['Por hacer', 'Urgente']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar nº o título…');
    expect(s.wrapper.find('[data-testid="task-view-mine"]').html()).toContain('Mis tareas');
  });
});

describe('TasksPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });

  it('«My tasks» too', async () => {
    const s = await setup();
    await ionValue(s.wrapper.find('[data-testid="task-views"]').element, 'mine', 'ionChange');
    expect(s.prop('testid')).toBe('task-mine');
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});

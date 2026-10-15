// TASK-F04 to F11 in the task's sheet: «TSK-… — Title» with its status and priority, the description,
// Due (red «Overdue» when past), Completed, Assigned to («Unassigned»), Project, Created and Created by;
// Status and Complete; Assign to (a person, searched) with Assign, Assign to me and Unassign; Edit and
// Delete; the subtasks with Open (and Back) and «Add subtask»; the comments, newest first, signed, with
// «Comment». Everything live; a refusal stays inside the sheet, next to what was typed.
import { Combo, ConfirmDialog, StatusPill } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, errorFrame, ionValue, mountTask, OWNER, page, settle } from '../__tests__/mount-task';
import { task } from '../__tests__/task';
import TaskFormModal from './TaskFormModal.vue';
import TaskSheet from './TaskSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { value?: unknown; disabled?: boolean; label?: string };

const DETAIL = 'task.task.detail';
const SUBTASKS = 'task.task.subtasks';
const COMMENTS = 'task.comment.list';
const MINE = 'staff.member.mine';

const TASK = task({
  description: 'Shelves too',
  status: 'in_progress',
  priority: 'urgent',
  due_date: '2020-01-01',
  assigned_to_id: 'm1',
  assignee_name: 'Ana López',
  project_id: 'p1',
  project_name: 'Opening',
  subtask_count: 1,
  comment_count: 2,
});
const SUB = task({ id: 't2', number: 'TSK-20261015-0002', title: 'Buy bleach', parent_id: 't1', status: 'todo' });
const COMMENTS_PAGE = page([
  { id: 'c2', task_id: 't1', text: 'Half done', author_id: 2, author_name: 'Bea Ruiz', created_at: '2026-10-15T10:30:00Z' },
  { id: 'c1', task_id: 't1', text: 'On it', author_id: null, author_name: null, created_at: '2026-10-15T09:00:00Z' },
]);

async function setup(options: { session?: typeof OWNER; locale?: 'en' | 'es'; detail?: unknown } = {}) {
  const m = await mountTask(TaskSheet, { props: { open: true, taskId: 't1' }, session: options.session, locale: options.locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  await m.live();
  await m.result(DETAIL, options.detail ?? TASK);
  await m.result(SUBTASKS, page([SUB]));
  await m.result(COMMENTS, COMMENTS_PAGE);
  await m.result(MINE, { member: { id: 'm9' } });
  const text = (id: string) => m.inDoc(id)?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
  const el = (id: string) => m.inDoc(id) as Control;
  return { ...m, text, el };
}

describe('TaskSheet', () => {
  it('follows the task, its subtasks and its comments live', async () => {
    const s = await setup();
    expect(s.params(DETAIL)).toEqual([{ id: 't1' }]);
    expect(s.params(SUBTASKS)).toEqual([{ id: 't1', limit: 100 }]);
    expect(s.params(COMMENTS)).toEqual([{ task_id: 't1', limit: 100 }]);
  });

  it('paints the head and the data of the task as the old detail', async () => {
    const s = await setup();
    expect(s.text('task-sheet-title')).toBe('TSK-20261015-0001 — Clean the store room');
    expect(s.wrapper.findAllComponents(StatusPill).slice(0, 2).map((p) => p.props('label'))).toEqual(['In Progress', 'Urgent']);
    expect(s.text('task-sheet-description')).toBe('Shelves too');
    expect(s.text('task-sheet-due')).toBe('Due: 01/01/2020');
    expect(s.el('task-sheet-due-value').getAttribute('aria-label')).toBe('Overdue');
    expect(s.text('task-sheet-completed')).toBe('Completed: —');
    expect(s.text('task-sheet-assignee')).toBe('Assigned to: Ana López');
    expect(s.text('task-sheet-project')).toBe('Project: Opening');
    expect(s.text('task-sheet-created-by')).toBe('Created by: Marta Jefa');
    expect(s.text('task-sheet-subtasks-heading')).toBe('Subtasks (1)');
    expect(s.text('task-sheet-comments-heading')).toBe('Comments (2)');
  });

  it('changes the status and completes', async () => {
    const s = await setup();
    s.answer(200, TASK);
    await ionValue(s.el('task-sheet-status'), 'blocked', 'ionChange');
    await click(s.el('task-sheet-complete'));
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([
      ['/api/task/tasks/set_status', { id: 't1', status: 'blocked' }],
      ['/api/task/tasks/complete', { id: 't1' }],
    ]);
  });

  it('cannot complete a closed task', async () => {
    const s = await setup({ detail: { ...TASK, status: 'done', completed_at: '2026-10-15T09:00:00Z' } });
    expect(s.el('task-sheet-complete').disabled).toBe(true);
    expect(s.text('task-sheet-completed')).toBe('Completed: 15/10/2026, 11:00');
    // A closed task is never painted as late.
    expect(s.el('task-sheet-due-value').getAttribute('aria-label')).toBeNull();
  });

  it('assigns the person chosen, assigns to me and unassigns', async () => {
    const s = await setup();
    s.answer(200, TASK);
    const assignTo = s.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === 'task-sheet-assign-to')!;
    expect(assignTo.props('label')).toBe('Assign to');
    expect(s.el('task-sheet-assign').disabled).toBe(true);
    assignTo.vm.$emit('update:modelValue', { id: 'm2', label: 'Bea Ruiz' });
    await settle();
    await click(s.el('task-sheet-assign'));
    await click(s.el('task-sheet-assign-me'));
    await click(s.el('task-sheet-unassign'));
    expect(s.sent().map((c) => c.body)).toEqual([{ id: 't1', member_id: 'm2' }, { id: 't1', to_me: true }, { id: 't1' }]);
  });

  it('does not offer «Assign to me» when it is already mine, nor «Unassign» when nobody has it', async () => {
    const s = await setup({ detail: { ...TASK, assigned_to_id: 'm9', assignee_name: 'Marta Jefa' } });
    expect(s.inDoc('task-sheet-assign-me')).toBeNull();
    const nobody = await setup({ detail: { ...TASK, assigned_to_id: null, assignee_name: null } });
    expect(nobody.inDoc('task-sheet-unassign')).toBeNull();
    expect(nobody.text('task-sheet-assignee')).toBe('Assigned to: Unassigned');
  });

  it('opens a subtask with Back to its parent', async () => {
    const s = await setup();
    expect(s.text('task-sheet-subtask-t2')).toContain('TSK-20261015-0002 — Buy bleach');
    await click(s.el('task-sheet-subtask-open-t2'));
    await s.reopen();
    expect(s.params(DETAIL)).toEqual([{ id: 't2' }]);
    await s.result(DETAIL, SUB);
    expect(s.text('task-sheet-trail')).toContain('TSK-20261015-0001 › TSK-20261015-0002');
    await click(s.el('task-sheet-back'));
    await s.reopen();
    expect(s.params(DETAIL)).toEqual([{ id: 't1' }]);
    expect(s.inDoc('task-sheet-back')).toBeNull();
  });

  it('adds a subtask under the task and empties the box once accepted', async () => {
    const s = await setup();
    s.answer(201, SUB);
    const box = s.el('task-sheet-new-subtask');
    expect(box.label).toBe('Add subtask');
    await ionValue(box, ' Buy bleach ', 'ionInput');
    await click(s.el('task-sheet-add-subtask'));
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([['/api/task/tasks', { title: 'Buy bleach', parent_id: 't1' }]]);
    expect(s.el('task-sheet-new-subtask').value).toBe('');
  });

  it('lists the comments newest first, signed and dated, and «Comment» empties the box once accepted', async () => {
    const s = await setup();
    expect(s.text('task-sheet-comment-c2')).toContain('Bea Ruiz · 15/10/2026, 12:30');
    expect(s.text('task-sheet-comment-c2')).toContain('Half done');
    expect(s.text('task-sheet-comment-c1')).toContain('anonymous');
    s.answer(201, { id: 'c3' });
    await ionValue(s.el('task-sheet-new-comment'), ' Finished ', 'ionInput');
    await click(s.el('task-sheet-add-comment'));
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([['/api/task/comments', { task_id: 't1', text: 'Finished' }]]);
    expect(s.el('task-sheet-new-comment').value).toBe('');
  });

  it('a refused comment stays in the box, with the reason inside the sheet', async () => {
    const s = await setup();
    s.answer(404, { error: { code: 'not_found', message: 'That task does not exist in this business.' } });
    await ionValue(s.el('task-sheet-new-comment'), 'Too late', 'ionInput');
    await click(s.el('task-sheet-add-comment'));
    expect(s.el('task-sheet-new-comment').value).toBe('Too late');
    expect(s.text('task-sheet-error')).toContain('That task does not exist in this business.');
  });

  it('Edit opens the form with the task; Delete asks first and closes the sheet', async () => {
    const s = await setup();
    await click(s.el('task-sheet-edit'));
    const form = s.wrapper.findComponent(TaskFormModal);
    expect([form.props('open'), form.props('task')]).toEqual([true, TASK]);
    await click(s.el('task-sheet-delete'));
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).at(-1)!;
    expect([dialog.props('title'), dialog.props('message')]).toEqual([
      'Delete task',
      'TSK-20261015-0001 Clean the store room will be deleted with its subtasks and comments. This cannot be undone.',
    ]);
    s.answer(200, { id: 't1' });
    dialog.vm.$emit('confirm');
    await settle();
    await settle();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/task/tasks/delete', body: { id: 't1' } });
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('an employee who may not change the task sees it, without the buttons that change it or Delete', async () => {
    const s = await setup({ session: EMPLOYEE, detail: { ...TASK, can_change: false } });
    for (const id of ['task-sheet-complete', 'task-sheet-add-comment', 'task-sheet-add-subtask']) expect(s.el(id).disabled, id).toBe(true);
    expect(s.inDoc('task-sheet-edit')).toBeNull();
    expect(s.inDoc('task-sheet-delete')).toBeNull();
  });

  it('says so when the task no longer exists', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(DETAIL), 'not_found'));
    await settle();
    expect(s.text('task-sheet-gone')).toBe('This task no longer exists.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.text('task-sheet-assignee')).toBe('Asignada a: Ana López');
    expect(s.text('task-sheet-subtasks-heading')).toBe('Subtareas (1)');
    expect(s.wrapper.findAllComponents(StatusPill)[0].props('label')).toBe('En curso');
  });
});

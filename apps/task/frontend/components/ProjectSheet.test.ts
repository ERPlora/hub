// TASK-F13 and F14 in the project's sheet (tasks#43): its name with its colour, Active or Inactive and
// its code; Name and Color editable with Save (only what changed); Deactivate / Activate, which keeps
// the saved name and colour; Delete, asked first; the 50 most recent tasks of the project with «Showing
// {shown} of {total}. Find the rest in Tasks.», and «Add task», which creates it inside the project.
// A refusal stays inside the sheet. An employee only reads it.
import { ConfirmDialog } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, errorFrame, ionValue, mountTask, OWNER, page, settle } from '../__tests__/mount-task';
import { project } from '../__tests__/project';
import { task } from '../__tests__/task';
import ProjectSheet from './ProjectSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { value?: unknown; disabled?: boolean; label?: string };

const DETAIL = 'task.project.detail';
const TASKS = 'task.task.list';
const TWO = page([task({ id: 't1', title: 'Paint' }), task({ id: 't2', number: 'TSK-20261015-0002', title: 'Sign', status: 'done' })]);

async function setup(options: { session?: typeof OWNER; locale?: 'en' | 'es'; detail?: unknown; tasks?: unknown } = {}) {
  const m = await mountTask(ProjectSheet, {
    props: { open: true, projectId: 'p1' },
    session: options.session,
    locale: options.locale,
    path: '/task/projects',
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  await m.live();
  await m.result(DETAIL, options.detail ?? project());
  if (options.tasks !== null) await m.result(TASKS, options.tasks ?? TWO);
  const text = (id: string) => m.inDoc(id)?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
  const el = (id: string) => m.inDoc(id) as Control;
  return { ...m, text, el };
}

describe('ProjectSheet', () => {
  it('follows the project and its 50 most recent tasks', async () => {
    const s = await setup();
    expect(s.params(DETAIL)).toEqual([{ id: 'p1' }]);
    expect(s.params(TASKS)).toEqual([{ project_id: 'p1', sort: '-created_at', limit: 50 }]);
    expect(s.text('task-project-sheet-title')).toBe('Opening');
    expect(s.text('task-project-sheet-state')).toBe('Active');
    expect(s.text('task-project-sheet-code')).toBe('Code: opening');
    expect(s.text('task-project-sheet-tasks-heading')).toBe('Tasks in this project (2)');
    expect(s.text('task-project-sheet-task-t2')).toContain('TSK-20261015-0002 — Sign');
    expect(s.text('task-project-sheet-task-t2')).toContain('Done');
  });

  it('says how many more tasks there are, and when there are none', async () => {
    const s = await setup({ tasks: page([task()], 70, 50) });
    expect(s.text('task-project-sheet-more')).toBe('Showing 1 of 70. Find the rest in Tasks.');
    const empty = await setup({ tasks: page([]) });
    expect(empty.text('task-project-sheet-tasks-empty')).toBe('No tasks in this project yet.');
  });

  it('says it is loading, and when the tasks cannot be loaded says so instead of «no tasks»', async () => {
    const s = await setup({ tasks: null });
    expect(s.text('task-project-sheet-tasks-loading')).toBe('Loading…');
    s.net.lastStream().push(errorFrame(s.subId(TASKS), 'boom'));
    await settle();
    expect(s.text('task-project-sheet-tasks-error')).toContain("Could not load this project's tasks");
    expect(s.inDoc('task-project-sheet-tasks-empty')).toBeNull();
  });

  it('Save sends only the name and colour that changed, trimmed', async () => {
    const s = await setup();
    s.answer(200, project({ name: 'Grand opening' }));
    expect(s.el('task-project-sheet-name').value).toBe('Opening');
    await ionValue(s.el('task-project-sheet-name'), ' Grand opening ', 'ionInput');
    await click(s.el('task-project-sheet-save'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/task/projects/update', query: {}, body: { id: 'p1', name: 'Grand opening' } }]);
  });

  it('never overwrites what someone else saved meanwhile: it sends only what this person changed', async () => {
    const s = await setup();
    s.answer(200, project({ color: '#000000' }));
    // Another person renames the project while the sheet is open: the untouched name follows it.
    await s.result(DETAIL, project({ name: 'Renamed by someone else' }), {}, 2);
    expect(s.el('task-project-sheet-name').value).toBe('Renamed by someone else');
    await ionValue(s.el('task-project-sheet-color'), '#000000', 'ionInput');
    await click(s.el('task-project-sheet-save'));
    expect(s.sent().map((c) => c.body)).toEqual([{ id: 'p1', color: '#000000' }]);
  });

  it('a name being typed is kept when someone else saves the project', async () => {
    const s = await setup();
    await ionValue(s.el('task-project-sheet-name'), 'Mine, half typed', 'ionInput');
    await s.result(DETAIL, project({ name: 'Renamed by someone else' }), {}, 2);
    expect(s.el('task-project-sheet-name').value).toBe('Mine, half typed');
  });

  it('a blank name is not sent', async () => {
    const s = await setup();
    await ionValue(s.el('task-project-sheet-name'), '  ', 'ionInput');
    expect(s.el('task-project-sheet-save').disabled).toBe(true);
  });

  it('Deactivate sends only is_active, whatever was typed, and an inactive project offers Activate', async () => {
    const s = await setup();
    s.answer(200, project({ is_active: false }));
    await ionValue(s.el('task-project-sheet-name'), 'Typed, not saved', 'ionInput');
    expect(s.text('task-project-sheet-toggle')).toBe('Deactivate');
    await click(s.el('task-project-sheet-toggle'));
    expect(s.sent().map((c) => c.body)).toEqual([{ id: 'p1', is_active: false }]);
    const inactive = await setup({ detail: project({ is_active: false }) });
    expect(inactive.text('task-project-sheet-state')).toBe('Inactive');
    expect(inactive.text('task-project-sheet-toggle')).toBe('Activate');
  });

  it('a refusal is painted inside the sheet, which stays open', async () => {
    const s = await setup();
    s.answer(404, { error: { code: 'not_found', message: 'That project does not exist in this business.' } });
    await ionValue(s.el('task-project-sheet-name'), 'New name', 'ionInput');
    await click(s.el('task-project-sheet-save'));
    expect(s.text('task-project-sheet-error')).toContain('That project does not exist in this business.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('«Add task» creates the task in this project and empties its box', async () => {
    const s = await setup();
    s.answer(201, task());
    await ionValue(s.el('task-project-sheet-new-task'), ' Hang the sign ', 'ionInput');
    await click(s.el('task-project-sheet-add-task'));
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([['/api/task/tasks', { title: 'Hang the sign', project_id: 'p1' }]]);
    expect(s.el('task-project-sheet-new-task').value).toBe('');
  });

  it('Delete asks first, then closes the sheet', async () => {
    const s = await setup();
    await click(s.el('task-project-sheet-delete'));
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('title'), dialog.props('message')]).toEqual([
      'Delete project',
      'Opening will be deleted. Its tasks stay, without a project.',
    ]);
    s.answer(200, { id: 'p1' });
    dialog.vm.$emit('confirm');
    await settle();
    await settle();
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([['/api/task/projects/delete', { id: 'p1' }]]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('an employee reads the project and may add a task, but not change or delete it', async () => {
    const s = await setup({ session: EMPLOYEE });
    for (const id of ['task-project-sheet-name', 'task-project-sheet-save', 'task-project-sheet-toggle', 'task-project-sheet-delete']) {
      expect(s.inDoc(id), id).toBeNull();
    }
    expect(s.inDoc('task-project-sheet-add-task')).not.toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.text('task-project-sheet-tasks-heading')).toBe('Tareas de este proyecto (2)');
    expect(s.text('task-project-sheet-toggle')).toBe('Desactivar');
  });
});

// TASK-F01 and TASK-F08: «New task» asks for Title (required), Description, Priority (Medium), Due,
// Assigned to (a person of the team, searched), Project (an active one, searched) and Tags, with
// «Create task», which cannot be pressed without a title. «Edit» opens «Editing task — {number}» with
// the task loaded and «Save», which sends only what changed (the assignee has its own buttons in the
// sheet). Refusals stay in the dialog, under their field.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { TaskOut } from '../operations';
import { click, ionValue, mountTask, settle } from '../__tests__/mount-task';
import TaskFormModal from './TaskFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

export const TASK: TaskOut = {
  id: 't1',
  number: 'TSK-20261015-0001',
  title: 'Clean the store room',
  description: 'Shelves too',
  status: 'todo',
  priority: 'high',
  project_id: 'p1',
  project_name: 'Opening',
  project_color: '#AA3300',
  parent_id: null,
  parent_number: null,
  parent_title: null,
  assigned_to_id: 'm1',
  assignee_name: 'Ana López',
  created_by_id: '01a16000-0000-7000-8000-0000000000b1',
  created_by_name: 'Marta',
  due_date: '2026-10-20',
  completed_at: null,
  tags: ['stock'],
  subtask_count: 0,
  comment_count: 0,
  created_at: '2026-10-15T08:00:00Z',
  updated_at: '2026-10-15T08:00:00Z',
  can_change: true,
};

async function setup(task: TaskOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountTask(TaskFormModal, { props: { open: false, task }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`task-form-${name}`) as Control;
  const save = () => m.inDoc('task-form-submit') as Control;
  const combo = (testid: string) => m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === testid);
  return { ...m, field, save, combo };
}

describe('TaskFormModal: New task', () => {
  it('asks for the fields of a task, Medium chosen, and cannot be created without a title', async () => {
    const s = await setup();
    expect(s.inDoc('task-form')?.getAttribute('aria-label')).toBe('New task');
    expect(['title', 'description', 'priority', 'due_date', 'tags'].map((name) => s.field(name).label)).toEqual([
      'Title',
      'Description',
      'Priority',
      'Due',
      'Tags',
    ]);
    expect(s.field('priority').value).toBe('medium');
    expect([s.combo('task-form-assignee')?.props('label'), s.combo('task-form-assignee')?.props('placeholder')]).toEqual([
      'Assigned to',
      'Unassigned',
    ]);
    expect([s.combo('task-form-project')?.props('label'), s.combo('task-form-project')?.props('placeholder')]).toEqual([
      'Project',
      'No project',
    ]);
    expect(s.save().textContent).toContain('Create task');
    expect(s.save().disabled).toBe(true);
  });

  it('creates the task with what was filled in, and closes', async () => {
    const s = await setup();
    s.answer(201, TASK);
    await ionValue(s.field('title'), ' Clean the store room ', 'ionInput');
    await ionValue(s.field('description'), 'Shelves too', 'ionInput');
    await ionValue(s.field('priority'), 'urgent', 'ionChange');
    await ionValue(s.field('due_date'), '2026-10-20', 'ionInput');
    await ionValue(s.field('tags'), 'stock, opening', 'ionInput');
    s.combo('task-form-assignee')!.vm.$emit('update:modelValue', { id: 'm1', label: 'Ana López' });
    s.combo('task-form-project')!.vm.$emit('update:modelValue', { id: 'p1', label: 'Opening' });
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/task/tasks',
        query: {},
        body: {
          title: 'Clean the store room',
          description: 'Shelves too',
          priority: 'urgent',
          due_date: '2026-10-20',
          assigned_to_id: 'm1',
          project_id: 'p1',
          tags: ['stock', 'opening'],
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a refusal of the server goes under its field and keeps what was typed', async () => {
    const s = await setup();
    const message = 'That person is not active in the team.';
    s.answer(422, { error: { code: 'invalid_field', message, fields: { assigned_to_id: message } } });
    await ionValue(s.field('title'), 'Mop', 'ionInput');
    s.combo('task-form-assignee')!.vm.$emit('update:modelValue', { id: 'm9', label: 'Ines' });
    await settle();
    await click(s.save());
    expect(s.combo('task-form-assignee')?.props('errorText')).toBe(message);
    expect(s.field('title').value).toBe('Mop');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });
});

describe('TaskFormModal: Editing task — {number}', () => {
  it('is named after the task, loaded, has no assignee field, and saves only what changed', async () => {
    const s = await setup(TASK);
    expect(s.inDoc('task-form')?.getAttribute('aria-label')).toBe('Editing task — TSK-20261015-0001');
    expect([s.field('title').value, s.field('priority').value, s.field('due_date').value, s.field('tags').value]).toEqual([
      'Clean the store room',
      'high',
      '2026-10-20',
      'stock',
    ]);
    expect(s.combo('task-form-assignee')).toBeUndefined();
    expect(s.combo('task-form-project')?.props('modelValue')).toEqual({ id: 'p1', label: 'Opening' });
    expect(s.save().textContent).toContain('Save');
    s.answer(200, TASK);
    await ionValue(s.field('due_date'), '', 'ionInput');
    s.combo('task-form-project')!.vm.$emit('update:modelValue', null);
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/task/tasks/update', query: {}, body: { id: 't1', due_date: null, project_id: null } },
    ]);
  });

  it('never overwrites what someone else saved meanwhile: it sends only what this person changed', async () => {
    const s = await setup(TASK);
    await ionValue(s.field('priority'), 'urgent', 'ionChange');
    // The sheet behind passes the live task: another person changes the description and the due day.
    await s.wrapper.setProps({ task: { ...TASK, description: 'Changed by someone else', due_date: '2026-11-01' } });
    await settle();
    // What this person typed stays.
    expect(s.field('priority').value).toBe('urgent');
    s.answer(200, TASK);
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/task/tasks/update', query: {}, body: { id: 't1', priority: 'urgent' } }]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(TASK, 'es');
    expect(s.inDoc('task-form')?.getAttribute('aria-label')).toBe('Editando tarea — TSK-20261015-0001');
    expect([s.field('title').label, s.field('due_date').label, s.combo('task-form-project')?.props('placeholder')]).toEqual([
      'Título',
      'Vence',
      'Sin proyecto',
    ]);
  });
});

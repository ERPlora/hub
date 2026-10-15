// TASK-F12: «New project» asks for Code (unique: «Code (q3-audit)»), Name and Color (optional, #RRGGBB),
// with «Create project», which cannot be pressed without code and name. A repeated code is said under
// the field, and what was typed stays.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountTask, settle } from '../__tests__/mount-task';
import ProjectFormModal from './ProjectFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; placeholder?: string };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountTask(ProjectFormModal, { props: { open: false }, locale, path: '/task/projects' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`task-project-form-${name}`) as Control;
  const save = () => m.inDoc('task-project-form-submit') as Control;
  return { ...m, field, save };
}

describe('ProjectFormModal', () => {
  it('asks for Code, Name and Color, and needs code and name', async () => {
    const s = await setup();
    expect(s.inDoc('task-project-form')?.getAttribute('aria-label')).toBe('New project');
    expect(['code', 'name', 'color'].map((name) => s.field(name).label)).toEqual(['Code', 'Name', 'Color']);
    expect([s.field('code').placeholder, s.field('color').placeholder]).toEqual(['Code (q3-audit)', 'Color (optional)']);
    expect(s.save().textContent).toContain('Create project');
    await ionValue(s.field('code'), 'q3', 'ionInput');
    expect(s.save().disabled).toBe(true);
    await ionValue(s.field('name'), 'Audit', 'ionInput');
    expect(s.save().disabled).toBe(false);
  });

  it('creates the project trimmed and closes', async () => {
    const s = await setup();
    s.answer(201, { id: 'p1' });
    await ionValue(s.field('code'), ' q3-audit ', 'ionInput');
    await ionValue(s.field('name'), ' Audit ', 'ionInput');
    await ionValue(s.field('color'), ' #AA3300 ', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/task/projects', query: {}, body: { code: 'q3-audit', name: 'Audit', color: '#AA3300' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a repeated code is said under its field', async () => {
    const s = await setup();
    const message = 'There is already a project with that code.';
    s.answer(409, { error: { code: 'task.project_exists', message, fields: { code: message } } });
    await ionValue(s.field('code'), 'q3', 'ionInput');
    await ionValue(s.field('name'), 'Audit', 'ionInput');
    await click(s.save());
    expect(s.field('code').errorText).toBe(message);
    expect(s.field('code').value).toBe('q3');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('task-project-form')?.getAttribute('aria-label')).toBe('Nuevo proyecto');
    expect(s.field('code').placeholder).toBe('Código (q3-audit)');
  });
});

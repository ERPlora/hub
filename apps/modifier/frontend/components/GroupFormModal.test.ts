// MODIFIER-F02 and F03: «New group» asks for the old screen's Name, «Kitchen ticket name», «Minimum (1 or
// more = required)» and «Maximum (0 = no ceiling)», plus «An option can be chosen more than once» and
// Order, with «Create»; Edit opens «Editing group — {name}» with «Save», which sends only what changed.
// A refusal goes under its field (a taken name, a maximum below the minimum) and what was typed stays.
import { describe, expect, it, vi } from 'vitest';

import type { GroupOut } from '../operations';
import { click, ionChecked, ionValue, mountModifier, settle } from '../__tests__/mount-modifier';
import GroupFormModal from './GroupFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; helperText?: string; disabled?: boolean };

const SAUCES: GroupOut = {
  id: 'g1',
  name: 'Sauces',
  kitchen_name: 'SAUCE',
  min_choices: 1,
  max_choices: 2,
  allow_repeat: false,
  is_required: true,
  sort_order: 3,
  option_count: 2,
  default_count: 0,
  link_count: 1,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
};

async function setup(group: GroupOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountModifier(GroupFormModal, { props: { open: false, group }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`modifier-group-form-${name}`) as Control;
  const save = () => m.inDoc('modifier-group-form-submit') as Control;
  return { ...m, field, save };
}

describe('GroupFormModal: New group', () => {
  it('asks for the old screen’s fields, plus repeat and order', async () => {
    const s = await setup();
    expect(s.inDoc('modifier-group-form')?.getAttribute('aria-label')).toBe('New group');
    expect(['name', 'kitchen_name', 'min_choices', 'max_choices', 'sort_order'].map((name) => s.field(name).label)).toEqual([
      'Name',
      'Kitchen ticket name',
      'Minimum (1 or more = required)',
      'Maximum (0 = no ceiling)',
      'Order',
    ]);
    expect(s.field('kitchen_name').helperText).toBe('Empty: the kitchen reads the name.');
    expect(s.field('allow_repeat').textContent).toContain('An option can be chosen more than once');
    expect([s.field('min_choices').value, s.field('max_choices').value, s.field('sort_order').value]).toEqual(['0', '0', '0']);
    expect(s.save().textContent).toContain('Create');
    expect(s.save().disabled).toBe(true);
  });

  it('sends modifier.group.create with what was typed, and closes', async () => {
    const s = await setup();
    s.answer(201, SAUCES);
    await ionValue(s.field('name'), ' Sauces ', 'ionInput');
    await ionValue(s.field('kitchen_name'), 'SAUCE', 'ionInput');
    await ionValue(s.field('min_choices'), '1', 'ionInput');
    await ionValue(s.field('max_choices'), '2', 'ionInput');
    await ionChecked(s.field('allow_repeat'), true);
    await ionValue(s.field('sort_order'), '3', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/modifier/groups',
        query: {},
        body: { name: 'Sauces', kitchen_name: 'SAUCE', min_choices: 1, max_choices: 2, allow_repeat: true, sort_order: 3 },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a refusal goes under its field, and what was typed stays', async () => {
    const s = await setup();
    const message = 'The maximum cannot be below the minimum (0 = no ceiling).';
    s.answer(422, { error: { code: 'invalid_payload', message, fields: { max_choices: message } } });
    await ionValue(s.field('name'), 'Sauces', 'ionInput');
    await ionValue(s.field('min_choices'), '3', 'ionInput');
    await ionValue(s.field('max_choices'), '1', 'ionInput');
    await click(s.save());
    expect(s.field('max_choices').errorText).toBe(message);
    expect(s.field('name').value).toBe('Sauces');
    expect(s.wrapper.emitted('update:open')?.at(-1)).not.toEqual([false]);
  });

  it('a number that is not whole is sent as typed, for the server to say why', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'invalid_payload', message: 'x', fields: { min_choices: 'Enter a whole number.' } } });
    await ionValue(s.field('name'), 'Sauces', 'ionInput');
    await ionValue(s.field('min_choices'), '1.5', 'ionInput');
    await click(s.save());
    expect((s.sent()[0].body as Record<string, unknown>).min_choices).toBe('1.5');
    expect(s.field('min_choices').errorText).toBe('Enter a whole number.');
  });
});

describe('GroupFormModal: Editing group — {name}', () => {
  it('is named after the group, loaded, and saves only what changed', async () => {
    const s = await setup(SAUCES);
    expect(s.inDoc('modifier-group-form')?.getAttribute('aria-label')).toBe('Editing group — Sauces');
    expect([s.field('name').value, s.field('kitchen_name').value, s.field('min_choices').value, s.field('max_choices').value]).toEqual([
      'Sauces',
      'SAUCE',
      '1',
      '2',
    ]);
    expect(s.save().textContent).toContain('Save');
    s.answer(200, { ...SAUCES, max_choices: 0 });
    await ionValue(s.field('max_choices'), '0', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/modifier/groups/update', query: {}, body: { id: 'g1', max_choices: 0 } }]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(SAUCES, 'es');
    expect(s.inDoc('modifier-group-form')?.getAttribute('aria-label')).toBe('Editando grupo — Sauces');
    expect(s.field('min_choices').label).toBe('Mínimo (1 o más = obligatorio)');
    expect(s.field('allow_repeat').textContent).toContain('Se puede repetir una opción');
  });
});

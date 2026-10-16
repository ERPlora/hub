// «Add a course» at the foot of the builder (COMBO-F05): Course name, «Minimum picks», «Maximum picks»
// (1 and 1 to start; 0 is no limit) and «The same option may be picked more than once», with «Save». It
// becomes «Course · {name}» to edit one, with «Cancel», and sends only what changed. A missing name or a
// ceiling below the floor is said before sending; a name the menu already has comes back under Name.
import { describe, expect, it } from 'vitest';

import { click, ionChecked, ionValue, mountCombo, settle } from '../__tests__/mount-combo';
import type { GroupOut } from '../operations';
import CourseForm from './CourseForm.vue';

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; checked?: boolean };

const COURSE: GroupOut = {
  id: 'g1',
  combo_id: 'm1',
  name: 'Mains',
  min_choices: 1,
  max_choices: 2,
  allow_repeat: false,
  sort_order: 3,
  options: [],
};

async function setup(course: GroupOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountCombo(CourseForm, { props: { comboId: 'm1', course }, locale });
  await settle();
  const field = (name: string) => m.inDoc(`combo-course-form-${name}`) as Control;
  return { ...m, field };
}

describe('CourseForm', () => {
  it('asks for the course as the old builder did, one compulsory pick to start', async () => {
    const s = await setup();
    expect(s.field('title').textContent?.trim()).toBe('Add a course');
    expect([s.field('name').label, s.field('min').label, s.field('max').label]).toEqual(['Course name', 'Minimum picks', 'Maximum picks']);
    expect([s.field('min').value, s.field('max').value, s.field('repeat').checked]).toEqual(['1', '1', false]);
    expect(s.inDoc('combo-course-form-cancel')).toBeNull();
  });

  it('adds the course to the menu and empties the form', async () => {
    const s = await setup();
    s.answer(201, COURSE);
    await ionValue(s.field('name'), ' Drinks ', 'ionInput');
    await ionValue(s.field('max'), '0', 'ionInput');
    await ionChecked(s.field('repeat'), true);
    await click(s.field('save'));
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/combo/groups',
        query: {},
        body: { combo_id: 'm1', name: 'Drinks', min_choices: 1, max_choices: 0, allow_repeat: true },
      },
    ]);
    expect(s.field('name').value).toBe('');
  });

  it('says what is missing before sending', async () => {
    const s = await setup();
    await click(s.field('save'));
    expect(s.field('reason').textContent).toContain('The course needs a name.');
    await ionValue(s.field('name'), 'Mains', 'ionInput');
    await ionValue(s.field('min'), '3', 'ionInput');
    await ionValue(s.field('max'), '2', 'ionInput');
    await click(s.field('save'));
    expect(s.field('reason').textContent).toContain('The maximum (2) is below the minimum (3): nobody could ever satisfy this course.');
    expect(s.sent()).toEqual([]);
  });

  it('a name the menu already has comes back under Name', async () => {
    const s = await setup();
    const message = 'That menu already has a course “Mains”.';
    s.answer(409, { error: { code: 'combo.group_exists', message, fields: { name: message } } });
    await ionValue(s.field('name'), 'Mains', 'ionInput');
    await click(s.field('save'));
    expect(s.field('name').errorText).toBe(message);
    expect(s.field('name').value).toBe('Mains');
  });

  it('edits a course, sending only what changed, and is done', async () => {
    const s = await setup(COURSE);
    expect(s.field('title').textContent?.trim()).toBe('Course · Mains');
    expect([s.field('name').value, s.field('min').value, s.field('max').value]).toEqual(['Mains', '1', '2']);
    s.answer(200, COURSE);
    await ionValue(s.field('min'), '2', 'ionInput');
    await click(s.field('save'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/combo/groups/update', query: {}, body: { id: 'g1', min_choices: 2 } }]);
    expect(s.wrapper.emitted('done')).toHaveLength(1);
    await click(s.field('cancel'));
    expect(s.wrapper.emitted('done')).toHaveLength(2);
  });

  it('speaks Spanish', async () => {
    const s = await setup(null, 'es');
    expect(s.field('title').textContent?.trim()).toBe('Añadir un plato');
    expect(s.field('repeat').textContent).toContain('Se puede elegir la misma opción más de una vez');
  });
});

// SERVICE-F07 «Crear y editar categorías»: «New category» asks for Name, Parent category («No parent
// (root)» or another one, searched on the server) and Order, with «Create category»; a row opens
// «Editing category — {name}» with «Save changes», which sends only what changed. A category is never
// offered as its own parent. A name already taken (409) goes under Name; what was typed stays.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { CategoryOut } from '../operations';
import { click, ionValue, mountService, page, settle } from '../__tests__/mount-service';
import CategoryFormModal from './CategoryFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

const COLOUR: CategoryOut = {
  id: 'c2',
  name: 'Colour',
  description: '',
  parent_id: 'c1',
  parent_name: 'Hair',
  icon: '',
  color: '',
  sort_order: 2,
  service_count: 3,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
};

async function setup(category: CategoryOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountService(CategoryFormModal, { props: { open: false, category }, locale, path: '/service/categories' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`service-category-form-${name}`) as Control;
  const save = () => m.inDoc('service-category-form-submit') as Control;
  const parent = () => m.wrapper.findComponent(Combo);
  return { ...m, field, save, parent };
}

describe('CategoryFormModal: New category', () => {
  it('asks for Name, Parent category and Order, as the old panel', async () => {
    const s = await setup();
    expect(s.inDoc('service-category-form')?.getAttribute('aria-label')).toBe('New category');
    expect([s.field('name').label, s.field('sort_order').label]).toEqual(['Name', 'Order']);
    expect([s.parent().props('label'), s.parent().props('placeholder')]).toEqual(['Parent category', 'No parent (root)']);
    expect(s.save().textContent).toContain('Create category');
    expect(s.save().disabled).toBe(true);
  });

  it('sends service.category.create with the parent picked and the order, and closes', async () => {
    const s = await setup();
    s.answer(201, COLOUR);
    await ionValue(s.field('name'), ' Colour ', 'ionInput');
    s.parent().vm.$emit('update:modelValue', { id: 'c1', label: 'Hair' });
    await ionValue(s.field('sort_order'), '2', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/service/categories', query: {}, body: { name: 'Colour', parent_id: 'c1', sort_order: 2 } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a name already taken goes under Name, and what was typed stays', async () => {
    const s = await setup();
    const message = 'There is already a category with that name. Pick another name.';
    s.answer(409, { error: { code: 'service.category_name_taken', message, fields: { name: message } } });
    await ionValue(s.field('name'), 'hair', 'ionInput');
    await click(s.save());
    expect(s.field('name').errorText).toBe(message);
    expect(s.field('name').value).toBe('hair');
  });

  it('the parent search never offers the category itself', async () => {
    const s = await setup(COLOUR);
    s.answerBy({ '/api/service/categories': [200, page([{ ...COLOUR }, { ...COLOUR, id: 'c1', name: 'Hair', parent_name: null }])] });
    const options = await (s.parent().props('search') as (q: string) => Promise<unknown[]>)('');
    expect(options).toEqual([{ id: 'c1', label: 'Hair' }]);
  });
});

describe('CategoryFormModal: Editing category — {name}', () => {
  it('is named after the category, loaded, and saves only what changed; no parent makes it a root', async () => {
    const s = await setup(COLOUR);
    expect(s.inDoc('service-category-form')?.getAttribute('aria-label')).toBe('Editing category — Colour');
    expect([s.field('name').value, s.field('sort_order').value, s.parent().props('modelValue')]).toEqual(['Colour', '2', { id: 'c1', label: 'Hair' }]);
    expect(s.save().textContent).toContain('Save changes');
    s.answer(200, { ...COLOUR, parent_id: null });
    s.parent().vm.$emit('update:modelValue', null);
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/service/categories/update', query: {}, body: { id: 'c2', parent_id: null } }]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(COLOUR, 'es');
    expect(s.inDoc('service-category-form')?.getAttribute('aria-label')).toBe('Editando categoría — Colour');
    expect(s.parent().props('placeholder')).toBe('Sin padre (raíz)');
  });
});

// COMBO-F02 «Crear un menú» and F03 «Cambiar los datos de un menú»: the old panel as a dialog. «New
// menu» asks for Name, Kitchen name, Closed price, «How is it sold?» (both consequences always shown,
// the chosen one stressed), the VAT category (only eaten in, searched in Taxes), the order and «On
// sale» (ticked). A menu eaten in without a VAT category is refused before it is sent. Editing sends
// only what changed. Refusals stay in the dialog, under their field.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { ComboOut } from '../operations';
import { click, ionChecked, ionValue, mountCombo, settle } from '../__tests__/mount-combo';
import MenuFormModal from './MenuFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; checked?: boolean };

const MENU: ComboOut = {
  id: 'm1',
  name: 'Menu of the day',
  kitchen_name: 'MENU',
  price: 1350,
  supply_kind: 'service',
  tax_category_key: 'restaurant.food',
  tax_category_name: 'Restaurant — food',
  sort_order: 2,
  is_active: true,
  group_count: 3,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
};

async function setup(combo: ComboOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountCombo(MenuFormModal, { props: { open: false, combo }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`combo-menu-form-${name}`) as Control;
  const save = () => m.inDoc('combo-menu-form-submit') as Control;
  const tax = () => m.wrapper.findComponent(Combo);
  return { ...m, field, save, tax };
}

describe('MenuFormModal: New menu', () => {
  it('asks what the old panel asked, eaten in and on sale by default', async () => {
    const s = await setup();
    expect(s.inDoc('combo-menu-form')?.getAttribute('aria-label')).toBe('New menu');
    expect([s.field('name').label, s.field('kitchen_name').label, s.field('price').label, s.field('supply_kind').label]).toEqual([
      'Name',
      'Kitchen name',
      'Closed price',
      'How is it sold?',
    ]);
    expect(s.field('supply_kind').value).toBe('service');
    expect(s.tax().props('label')).toBe('VAT category');
    expect(s.field('sort_order').label).toBe('Order on the menu list');
    expect(s.field('is_active').checked).toBe(true);
    // Both consequences on the table, the chosen one stressed.
    expect(s.field('help-service').dataset.active).toBe('true');
    expect(s.field('help-goods').dataset.active).toBe('false');
    expect(s.save().disabled).toBe(true);
  });

  it('to take away asks for no VAT category of its own', async () => {
    const s = await setup();
    await ionValue(s.field('supply_kind'), 'goods');
    expect(s.wrapper.findComponent(Combo).exists()).toBe(false);
    expect(s.field('help-goods').dataset.active).toBe('true');
  });

  it('sends combo.combo.create with the price in cents and the VAT category, and closes', async () => {
    const s = await setup();
    s.answer(201, { ...MENU, groups: [], sellable: false, blockers: [] });
    await ionValue(s.field('name'), ' Menu of the day ', 'ionInput');
    await ionValue(s.field('price'), '13,50', 'ionInput');
    s.tax().vm.$emit('update:modelValue', { id: 'restaurant.food', label: 'Restaurant — food · 10%' });
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/combo/combos',
        query: {},
        body: {
          name: 'Menu of the day',
          kitchen_name: '',
          price: 1350,
          supply_kind: 'service',
          tax_category_key: 'restaurant.food',
          sort_order: 0,
          is_active: true,
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a menu eaten in without a VAT category is refused under the picker, before anything is sent', async () => {
    const s = await setup();
    await ionValue(s.field('name'), 'Menu', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.tax().props('errorText')).toBe('A menu eaten in needs its own VAT category: without it, it cannot be billed.');
  });

  it('an amount that is not one is refused, never read as 0', async () => {
    const s = await setup();
    await ionValue(s.field('name'), 'Pack', 'ionInput');
    await ionValue(s.field('supply_kind'), 'goods');
    await ionValue(s.field('price'), '1.250', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.field('price').errorText).toContain('This amount can be read in two ways');
  });

  it('the server’s refusal of a field goes under it, and what was typed stays', async () => {
    const s = await setup();
    const message = 'That tax category does not exist in Taxes.';
    s.answer(422, { error: { code: 'invalid_field', message, fields: { tax_category_key: message } } });
    await ionValue(s.field('name'), 'Menu', 'ionInput');
    s.tax().vm.$emit('update:modelValue', { id: 'gone.key', label: 'Gone' });
    await settle();
    await click(s.save());
    expect(s.tax().props('errorText')).toBe(message);
    expect(s.field('name').value).toBe('Menu');
  });
});

describe('MenuFormModal: editing', () => {
  it('opens with the menu and sends only what changed', async () => {
    const s = await setup(MENU);
    expect(s.inDoc('combo-menu-form')?.getAttribute('aria-label')).toBe('Menu · Menu of the day');
    expect([s.field('name').value, s.field('price').value, s.field('sort_order').value]).toEqual(['Menu of the day', '13.50', '2']);
    expect(s.tax().props('modelValue')).toEqual({ id: 'restaurant.food', label: 'Restaurant — food' });
    s.answer(200, { ...MENU, price: 1400, groups: [], sellable: true, blockers: [] });
    await ionValue(s.field('price'), '14', 'ionInput');
    await ionChecked(s.field('is_active'), false);
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/combo/combos/update', query: {}, body: { id: 'm1', price: 1400, is_active: false } }]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(MENU, 'es');
    expect(s.inDoc('combo-menu-form')?.getAttribute('aria-label')).toBe('Menú · Menu of the day');
    expect([s.field('price').label, s.field('supply_kind').label]).toEqual(['Precio cerrado', '¿Cómo se vende?']);
    expect(s.field('price').value).toBe('13,50');
  });
});

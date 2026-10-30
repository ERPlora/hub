// COMBO-F02 «Crear un menú» and F03 «Cambiar los datos de un menú»: the old panel as a dialog. «New
// menu» asks for Name, Kitchen name, Closed price, «How is it sold?» (both consequences always shown,
// the chosen one stressed), the VAT category (only eaten in, searched in Taxes), the order and «On
// sale» (ticked). A menu eaten in without a VAT category is refused before it is sent. Editing sends
// only what changed. Refusals stay in the dialog, under their field. The closed price is in the business's currency
// («Closed price (PLN)», with its decimals); just «Closed price» while the business has not answered.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { Business } from '../../../../base/frontend/operations';
import type { ComboOut } from '../operations';
import { business, click, ionChecked, ionValue, JAPANESE, mountCombo, POLISH, settle } from '../__tests__/mount-combo';
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

/** `answer`: what the business answers when the stream opens (`null`: it opens and the business does not answer
 *  yet); without it, the stream never opens. */
async function setup(combo: ComboOut | null = null, locale: 'en' | 'es' = 'en', answer?: Business | null) {
  const m = await mountCombo(MenuFormModal, { props: { open: false, combo }, locale, business: answer });
  if (answer !== undefined) await m.live();
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

describe('MenuFormModal: in the business’s currency', () => {
  it('in Poland the closed price is in złoty: the field says PLN and «13,50 zł» is 1350 grosze', async () => {
    const s = await setup(null, 'en', business(POLISH));
    expect(s.field('price').label).toBe('Closed price (PLN)');
    s.answer(201, { ...MENU, groups: [], sellable: false, blockers: [] });
    await ionValue(s.field('name'), 'Menu of the day', 'ionInput');
    await ionValue(s.field('price'), '13,50 zł', 'ionInput');
    s.tax().vm.$emit('update:modelValue', { id: 'restaurant.food', label: 'Restaurant — food · 10%' });
    await settle();
    await click(s.save());
    expect(s.sent().map((call) => (call.body as { price: number }).price)).toEqual([1350]);
  });

  it('a euro amount is never read as złoty: the field says it is not an amount and nothing is sent', async () => {
    const s = await setup(null, 'es', business(POLISH));
    expect(s.field('price').label).toBe('Precio cerrado (PLN)');
    await ionValue(s.field('name'), 'Menú', 'ionInput');
    await ionValue(s.field('supply_kind'), 'goods');
    await ionValue(s.field('price'), '13,50 €', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.field('price').errorText).toBe('Esto no es un importe. Escribe una cifra, por ejemplo 12,50.');
  });

  it('in yen the price has no decimals: it opens as «1350» and «1400» is saved as 1400', async () => {
    const s = await setup(MENU, 'en', business(JAPANESE));
    expect(s.field('price').value).toBe('1350');
    s.answer(200, { ...MENU, price: 1400, groups: [], sellable: true, blockers: [] });
    await ionValue(s.field('price'), '1400', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/combo/combos/update', query: {}, body: { id: 'm1', price: 1400 } }]);
  });

  it('opened before the business answers, an untouched price is rewritten with its currency’s decimals when it arrives', async () => {
    const s = await setup(MENU, 'en', null);
    expect([s.field('price').label, s.field('price').value]).toEqual(['Closed price', '13.50']);
    await s.result('base.business.get', business(JAPANESE));
    expect([s.field('price').label, s.field('price').value]).toEqual(['Closed price (JPY)', '1350']);
    // Nothing changed: saving sends nothing about the price.
    s.answer(200, { ...MENU, is_active: false, groups: [], sellable: true, blockers: [] });
    await ionChecked(s.field('is_active'), false);
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/combo/combos/update', query: {}, body: { id: 'm1', is_active: false } }]);
  });

  it('what the person typed before the business answers stays as typed, and is read in its currency', async () => {
    const s = await setup(MENU, 'en', null);
    await ionValue(s.field('price'), '1500', 'ionInput');
    await s.result('base.business.get', business(JAPANESE));
    expect(s.field('price').value).toBe('1500');
    s.answer(200, { ...MENU, price: 1500, groups: [], sellable: true, blockers: [] });
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/combo/combos/update', query: {}, body: { id: 'm1', price: 1500 } }]);
  });
});

// COMBO-F14: «Photo» in «Edit details» of a menu, like an item's (INVENTORY-F30/F31): a library image (searched by the
// menu's name) or a photo of its own, sent once the menu is saved; if the menu saved and the photo did not, the dialog
// says so with «Retry», which sends only the photo, and the menu keeps the photo it had.
describe('MenuFormModal: photo', () => {
  const DETAIL = { ...MENU, groups: [], sellable: false, blockers: [] };
  const MENU_DIA = { reference: 'catalog:hospitality/menu_dia', folder: 'hospitality', name: 'menu_dia', title: 'Menú del día', url: '/p/catalog/hospitality/menu_dia.webp' };
  const WITH_PHOTO: ComboOut = { ...MENU, image: 'catalog:hospitality/menu_dia', image_url: MENU_DIA.url };
  const writes = (s: Awaited<ReturnType<typeof setup>>) => s.sent().filter((call) => call.method === 'POST');

  async function chooseFile(s: Awaited<ReturnType<typeof setup>>, file: File) {
    const input = s.inDoc('combo-menu-form-image-file') as HTMLInputElement;
    Object.defineProperty(input, 'files', { configurable: true, value: [file] });
    input.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(s.inDoc('combo-menu-form-image-preview')?.querySelector('img')?.getAttribute('src')).toMatch(/^data:/));
  }

  it('shows «Photo» with the menu’s photo, or its initials', async () => {
    const s = await setup(WITH_PHOTO);
    expect(s.inDoc('combo-menu-form-image-label')?.textContent?.trim()).toBe('Photo');
    expect(s.inDoc('combo-menu-form-image-preview')?.querySelector('img')?.getAttribute('src')).toBe(MENU_DIA.url);
  });

  it('a new menu with a library image: searched by its name, set once it is created', async () => {
    const s = await setup();
    s.answerBy({
      '/api/catalog/images': [200, { rows: [MENU_DIA], total: 1, limit: 60, offset: 0 }],
      '/api/combo/combos': [201, DETAIL],
      '/api/combo/combos/image': [200, DETAIL],
    });
    await ionValue(s.field('name'), 'Menú del día', 'ionInput');
    await ionValue(s.field('price'), '13,50', 'ionInput');
    s.tax().vm.$emit('update:modelValue', { id: 'restaurant.food', label: 'Restaurant — food · 10%' });
    await settle();
    await click(s.inDoc('combo-menu-form-image-library'));
    await settle();
    expect(s.sent().find((call) => call.path === '/api/catalog/images')?.query.query).toBe('Menú del día');
    await click(s.inDoc('combo-menu-form-image-library-modal-image-hospitality-menu_dia'));
    await click(s.save());
    await settle();
    expect(writes(s).map((call) => [call.path, call.body])).toEqual([
      ['/api/combo/combos', expect.objectContaining({ name: 'Menú del día' })],
      ['/api/combo/combos/image', { id: 'm1', image: 'catalog:hospitality/menu_dia' }],
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a photo of its own that fails: the menu saved, «Retry» sends only the photo; in Spanish', async () => {
    const s = await setup(WITH_PHOTO, 'es');
    s.answerBy({
      '/api/combo/combos/update': [200, DETAIL],
      '/api/combo/combos/image/upload': [422, { error: { code: 'base.photo_invalid', message: 'Ese archivo no es una foto. Sube una imagen JPG, PNG o WebP.' } }],
    });
    await chooseFile(s, new File(['ABC'], 'mine.png', { type: 'image/png' }));
    await click(s.save());
    await vi.waitFor(() => expect(s.inDoc('combo-menu-form-photo-failed')).not.toBeNull());
    expect(s.inDoc('combo-menu-form-photo-failed')?.textContent).toContain(
      'El menú se ha guardado, pero la foto no: Ese archivo no es una foto. Sube una imagen JPG, PNG o WebP.',
    );
    expect(s.save().disabled).toBe(true);
    s.answerBy({ '/api/combo/combos/image/upload': [200, DETAIL] });
    await click(s.inDoc('combo-menu-form-photo-retry'));
    await vi.waitFor(() => expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]));
    expect(writes(s).map((call) => call.path)).toEqual([
      '/api/combo/combos/update',
      '/api/combo/combos/image/upload',
      '/api/combo/combos/image/upload',
    ]);
  });

  it('«Remove photo» clears it when saved', async () => {
    const s = await setup(WITH_PHOTO);
    s.answerBy({ '/api/combo/combos/update': [200, DETAIL], '/api/combo/combos/image': [200, DETAIL] });
    await click(s.inDoc('combo-menu-form-image-remove'));
    await click(s.save());
    await settle();
    expect(writes(s).map((call) => call.body)).toEqual([{ id: 'm1' }, { id: 'm1', image: '' }]);
  });

  it('closing without saving discards the photo chosen; opening another menu shows its own', async () => {
    const s = await setup(WITH_PHOTO);
    await click(s.inDoc('combo-menu-form-image-remove'));
    expect(s.inDoc('combo-menu-form-image-preview')?.querySelector('img')).toBeNull();
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    await settle();
    expect(s.inDoc('combo-menu-form-image-preview')?.querySelector('img')?.getAttribute('src')).toBe(MENU_DIA.url);
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ combo: { ...MENU, id: 'm2', name: 'Kids menu' }, open: true });
    await settle();
    expect(s.inDoc('combo-menu-form-image-preview')?.querySelector('img')).toBeNull();
    expect(s.inDoc('combo-menu-form-image-preview')?.textContent?.trim()).toBe('KM');
  });
});

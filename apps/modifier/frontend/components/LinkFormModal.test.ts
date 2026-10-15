// MODIFIER-F05: «Add product or category» opens «Apply «{group}» to…»: Product or Category, and the search
// of each in Inventory (a product by its name or SKU). «Apply» sends `modifier.link.attach` with the id
// picked; a link that already exists is said in the dialog.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { GroupOut } from '../operations';
import { click, mountModifier, page, settle } from '../__tests__/mount-modifier';
import LinkFormModal from './LinkFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { value?: unknown; disabled?: boolean };

const SAUCES = { id: 'g1', name: 'Sauces' } as GroupOut;

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountModifier(LinkFormModal, { props: { open: false, group: SAUCES }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const kind = () => m.inDoc('modifier-link-form-kind') as Control;
  const save = () => m.inDoc('modifier-link-form-submit') as Control;
  const target = () => m.wrapper.findComponent(Combo);
  async function pickKind(value: 'product' | 'category') {
    kind().dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true }));
    await settle();
  }
  return { ...m, kind, save, target, pickKind };
}

describe('LinkFormModal', () => {
  it('is named after the group and starts with a product', async () => {
    const s = await setup();
    expect(s.inDoc('modifier-link-form')?.getAttribute('aria-label')).toBe('Apply «Sauces» to…');
    expect(s.kind().value).toBe('product');
    expect(s.target().props('label')).toBe('Product (name or SKU)');
    expect(s.save().textContent).toContain('Apply');
    expect(s.save().disabled).toBe(true);
  });

  it('searches the products of Inventory and links the one picked', async () => {
    const s = await setup();
    s.answerBy({ '/api/inventory/products': [200, page([{ id: 'p1', name: 'Burger', sku: 'BUR-01' }])] });
    const options = await (s.target().props('search') as (q: string) => Promise<unknown[]>)('bur');
    expect(options).toEqual([{ id: 'p1', label: 'Burger', hint: 'BUR-01' }]);
    s.target().vm.$emit('update:modelValue', options[0]);
    await settle();
    s.answer(201, { id: 'l1' });
    await click(s.save());
    expect(s.sent().at(-1)).toEqual({ method: 'POST', path: '/api/modifier/links/attach', query: {}, body: { group_id: 'g1', product_id: 'p1' } });
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('or a category, picked afresh when the kind changes', async () => {
    const s = await setup();
    s.target().vm.$emit('update:modelValue', { id: 'p1', label: 'Burger' });
    await s.pickKind('category');
    expect(s.target().props('modelValue')).toBeNull();
    expect(s.target().props('label')).toBe('Category');
    s.answerBy({ '/api/inventory/categories': [200, page([{ id: 'c1', name: 'Mains' }])] });
    const options = await (s.target().props('search') as (q: string) => Promise<unknown[]>)('ma');
    s.target().vm.$emit('update:modelValue', options[0]);
    await settle();
    s.answer(201, { id: 'l2' });
    await click(s.save());
    expect(s.sent().at(-1)?.body).toEqual({ group_id: 'g1', category_id: 'c1' });
  });

  it('a link that already exists is said in the dialog', async () => {
    const s = await setup();
    const message = 'This group already applies there.';
    s.target().vm.$emit('update:modelValue', { id: 'p1', label: 'Burger' });
    await settle();
    s.answer(409, { error: { code: 'modifier.link_exists', message, fields: { __all__: message } } });
    await click(s.save());
    expect(s.inDoc('modifier-link-form-error')?.textContent).toContain(message);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('modifier-link-form')?.getAttribute('aria-label')).toBe('Aplicar «Sauces» a…');
    expect(s.target().props('label')).toBe('Producto (nombre o SKU)');
  });
});

// TAX-F02 (create a category of the business's own): the «+» of Categories opens this dialog — Key, Name and
// Description, «Add». It closes when the server saved the category (the live list paints it); a
// refusal keeps it open with each message under its field (a malformed key, a 422; a key that
// exists, the 409 `tax.category_exists` under Key) and nothing is lost of what was typed.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountTax, settle } from '../__tests__/mount-tax';
import CategoryCreateModal from './CategoryCreateModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; placeholder?: string; fill?: string; errorText?: string; disabled?: boolean };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountTax(CategoryCreateModal, { props: { open: true }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const field = (name: string) => m.inDoc(`tax-category-form-${name}`) as Control;
  const add = () => m.inDoc('tax-category-form-submit') as Control;
  async function fill(values: Record<string, string>) {
    for (const [name, value] of Object.entries(values)) await ionValue(field(name), value, 'ionInput');
  }
  return { ...m, field, add, fill };
}

describe('CategoryCreateModal (TAX-F02)', () => {
  it('asks for Key, Name and Description in outlined md boxes, under «New tax category», with «Add»', async () => {
    const s = await setup();
    expect(s.inDoc('tax-category-form')?.getAttribute('aria-label')).toBe('New tax category');
    expect(['key', 'name', 'description'].map((n) => [s.field(n).label, s.field(n).placeholder, s.field(n).fill, s.field(n).getAttribute('mode')])).toEqual([
      ['Key', 'restaurant.food', 'outline', 'md'],
      ['Name', 'general VAT', 'outline', 'md'],
      ['Description', 'optional', 'outline', 'md'],
    ]);
    expect(s.add().textContent?.trim()).toBe('Add');
  });

  it('«Add» waits for a key and a name', async () => {
    const s = await setup();
    expect(s.add().disabled).toBe(true);
    await s.fill({ key: 'product.books' });
    expect(s.add().disabled).toBe(true);
    await s.fill({ name: 'Books' });
    expect(s.add().disabled).toBe(false);
  });

  it('sends tax.category.create with what was typed, then closes and starts blank again', async () => {
    const s = await setup();
    s.answer(201, { id: 'c9', key: 'product.books', name: 'Books' });
    await s.fill({ key: ' product.books ', name: 'Books', description: 'Printed books' });
    await click(s.add());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/tax/categories', query: {}, body: { key: 'product.books', name: 'Books', description: 'Printed books' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    await s.wrapper.setProps({ open: true });
    await settle();
    expect(s.field('key').value).toBe('');
  });

  it('a malformed key (422) is said under Key, the dialog stays open with what was typed', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'invalid_payload', message: 'Some fields are not valid.', fields: { key: 'String should match pattern' } } });
    await s.fill({ key: 'Bad Key', name: 'Books' });
    await click(s.add());
    expect(s.field('key').errorText).toBe('String should match pattern');
    expect(s.field('key').classList.contains('ion-invalid')).toBe(true);
    expect(s.field('name').classList.contains('ion-invalid')).toBe(false);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    expect(s.field('key').value).toBe('Bad Key');
  });

  it('a key that exists (409) is said under Key with the server’s words, and on top', async () => {
    const s = await setup();
    const message = 'There is already a tax category with that key.';
    s.answer(409, { error: { code: 'tax.category_exists', message, fields: { key: message } } });
    await s.fill({ key: 'restaurant.food', name: 'Food' });
    await click(s.add());
    expect(s.field('key').errorText).toBe(message);
    expect(s.inDoc('tax-category-form-error')?.textContent).toContain(message);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('tax-category-form')?.getAttribute('aria-label')).toBe('Nueva categoría fiscal');
    expect(['key', 'name', 'description'].map((n) => s.field(n).label)).toEqual(['Clave', 'Nombre', 'Descripción']);
    expect(s.field('name').placeholder).toBe('IVA general');
    expect(s.add().textContent?.trim()).toBe('Añadir');
  });
});

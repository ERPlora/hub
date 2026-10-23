// The category form (WORKBOOK «Categorías», INVENTORY-F06): «New category» or «Editing category —
// <name>» with Name, «Slug (optional)» and «Tax rate» («— (default)» or a tax category). «Save» /
// «Save changes» is off without a name; an edit sends only what changed (what the screen does not
// show — description, icon, colour, order — is left as it is); a refusal stays in the dialog with each
// message under its field; «Cancel editing» leaves the category as it was.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { category, flush, mountInventory, ok, refusal, TAX_CATEGORIES } from '../__tests__/mount-inventory';
import CategoryFormModal from './CategoryFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

type Control = HTMLElement & { value?: unknown; errorText?: string; disabled?: boolean; label?: string };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(CategoryFormModal, {
    props: { open: true, category: null, ...props },
    locale,
    attach: true,
    api: () => ok(TAX_CATEGORIES),
  });
  const call = await m.live();
  await m.result(call, 'tax.category.list', TAX_CATEGORIES);
  const el = <T extends HTMLElement = Control>(id: string) => document.querySelector<T>(`[data-testid="${id}"]`);
  /** Types into an Ionic field as a person does (`ionInput` with the value). */
  async function type(id: string, value: string) {
    const field = el(id)!;
    (field as Control).value = value;
    field.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  /** «Tax rate» is a Combo of @erplora/ui: what it offers on opening, as [key, label]. */
  const combo = () => m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === 'inventory-category-tax')!;
  const offers = async () => (await (combo().props('search') as (q: string) => Promise<ComboOption[]>)('')).map((o) => [o.id, o.label]);
  async function pickTax(key: string) {
    const option = (await (combo().props('search') as (q: string) => Promise<ComboOption[]>)('')).find((o) => o.id === key);
    if (!option) throw new Error(`«Tax rate» offers no ${key}`);
    combo().vm.$emit('update:modelValue', option);
    await flush();
  }
  async function submit() {
    el('inventory-category-form-submit')!.click();
    await flush();
  }
  return { ...m, el, type, combo, offers, pickTax, submit };
}

describe('CategoryFormModal', () => {
  it('«New category»: Name, Slug (optional), Tax rate with «— (default)»; Save off without a name', async () => {
    const s = await setup();
    expect(s.el('inventory-category-form')?.getAttribute('aria-label')).toBe('New category');
    expect([(s.el('inventory-category-name') as Control).label, (s.el('inventory-category-slug') as Control).label]).toEqual([
      'Name',
      'Slug (optional)',
    ]);
    expect((await s.offers())[0]).toEqual(['', '— (default)']);
    expect(s.combo().props('modelValue')).toEqual({ id: '', label: '— (default)' });
    expect(s.el('inventory-category-form-submit')?.textContent?.trim()).toBe('Save');
    expect((s.el('inventory-category-form-submit') as Control).disabled).toBe(true);
  });

  it('creates it with what was typed, an empty tax as none, and closes', async () => {
    const s = await setup();
    await s.type('inventory-category-name', ' Wines ');
    await s.pickTax('product.generic');
    s.net.onApi(() => ok(category({ id: 'c9', name: 'Wines' }), 201));
    await s.submit();
    const [call] = s.calls('/api/inventory/categories');
    expect(call.init.method).toBe('POST');
    // No slug typed: none is sent, and the server makes it from the name.
    expect(s.body(call)).toEqual({ name: 'Wines', tax_category_key: 'product.generic' });
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('without a tax rate sends none', async () => {
    const s = await setup();
    s.net.onApi(() => ok(category(), 201));
    await s.type('inventory-category-name', 'Drinks');
    await s.type('inventory-category-slug', 'bar');
    await s.submit();
    expect(s.body(s.calls('/api/inventory/categories')[0])).toEqual({ name: 'Drinks', slug: 'bar', tax_category_key: null });
  });

  it('editing: «Editing category — <name>», its values, and only what changed is sent', async () => {
    const s = await setup({ category: category({ tax_category_key: 'product.generic' }) });
    expect(s.el('inventory-category-form')?.getAttribute('aria-label')).toBe('Editing category — Drinks');
    expect([(s.el('inventory-category-name') as Control).value, (s.el('inventory-category-slug') as Control).value]).toEqual(['Drinks', 'drinks']);
    expect(s.el('inventory-category-form-submit')?.textContent?.trim()).toBe('Save changes');
    expect(s.el('inventory-category-form-cancel')?.textContent?.trim()).toBe('Cancel editing');
    await s.type('inventory-category-name', 'Bar');
    await s.pickTax('');
    s.net.onApi(() => ok(category({ name: 'Bar' })));
    await s.submit();
    const [call] = s.calls('/api/inventory/categories/update');
    expect(s.body(call)).toEqual({ id: 'c1', name: 'Bar', tax_category_key: '' });
  });

  it('editing: a slug emptied by hand is not sent, so the category keeps its own', async () => {
    const s = await setup({ category: category() });
    s.net.onApi(() => ok(category()));
    await s.type('inventory-category-slug', '');
    await s.type('inventory-category-name', 'Bar');
    await s.submit();
    expect(s.body(s.calls('/api/inventory/categories/update')[0])).toEqual({ id: 'c1', name: 'Bar' });
  });

  it('a refusal stays in the dialog: its message on top and each field message under its field', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(422, 'invalid_payload', 'Invalid payload', { slug: 'Use lowercase letters, digits and dashes.' }));
    await s.type('inventory-category-name', 'Wines');
    await s.type('inventory-category-slug', 'Bad Slug');
    await s.submit();
    expect((s.el('inventory-category-slug') as Control).errorText).toBe('Use lowercase letters, digits and dashes.');
    expect(s.el('inventory-category-form-error')?.textContent).toContain('Invalid payload');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ category: category() }, 'es');
    expect(s.el('inventory-category-form')?.getAttribute('aria-label')).toBe('Editando categoría — Drinks');
    expect((s.el('inventory-category-tax') as Control).label).toBe('Tipo de IVA / Impuesto');
    expect(s.el('inventory-category-form-cancel')?.textContent?.trim()).toBe('Cancelar edición');
  });
});

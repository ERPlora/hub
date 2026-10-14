// TAX-F14 (teach a category alias by hand): the «+» of Aliases opens this dialog — the Alias (the
// outside text), the Category CHOSEN among all the business's, searched on the server (never typed: a
// wrong key would put the wrong VAT on an import) and the Origin, «Learned» to begin with; «Add». A
// repeated alias (409) is said under Alias; the dialog closes when the server saved it.
import { describe, expect, it, vi } from 'vitest';

import type { CategoryRowOut } from '../operations';
import { click, ionValue, mountTax, settle } from '../__tests__/mount-tax';
import AliasCreateModal from './AliasCreateModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; placeholder?: string; fill?: string; errorText?: string; disabled?: boolean };

const category = (key: string, display: string): CategoryRowOut => ({
  id: key,
  key,
  name: display,
  description: '',
  display_name: display,
  display_description: '',
  is_system: true,
  is_active: true,
  rate_pct: '10.00',
  operation_class: 'subject',
});
const CATEGORIES = [category('restaurant.food', 'Restauración — comida'), category('product.generic', 'Producto — general')];
const CATEGORY_PAGE = { rows: CATEGORIES, total: 2, limit: 50, offset: 0 };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountTax(AliasCreateModal, { props: { open: true }, locale, path: '/tax/aliases' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  await m.live();
  await m.result('tax.category.list', CATEGORY_PAGE);
  const field = (name: string) => m.inDoc(`tax-alias-form-${name}`) as Control;
  const add = () => m.inDoc('tax-alias-form-submit') as Control;
  const options = (name: string) =>
    [...field(name).querySelectorAll('ion-select-option')].map((o) => [(o as Control).value, o.textContent?.trim()]);
  /** Opens the category list and returns its choices. */
  async function categories() {
    await click(field('category'));
    return m.wrapper.findAll('[data-testid="tax-alias-form-category-option"]').map((o) => [o.attributes('data-value'), o.text().trim()]);
  }
  async function chooseCategory(value: string) {
    await click(field('category'));
    await click(m.wrapper.get(`[data-testid="tax-alias-form-category-option"][data-value="${value}"]`).element);
  }
  return { ...m, field, add, options, categories, chooseCategory };
}

describe('AliasCreateModal (TAX-F14)', () => {
  it('asks for the Alias, the Category among the business’s, and the Origin («Learned» first)', async () => {
    const s = await setup();
    expect(s.inDoc('tax-alias-form')?.getAttribute('aria-label')).toBe('New category alias');
    expect([s.field('alias').label, s.field('alias').placeholder, s.field('alias').fill]).toEqual(['Alias', 'food', 'outline']);
    expect([s.field('category').tagName, s.field('category').label, s.field('category').placeholder]).toEqual([
      'ION-INPUT',
      'Category',
      'Choose a category',
    ]);
    expect(s.params('tax.category.list')).toEqual([{ sort: 'display_name', dir: 'asc', limit: 50 }]);
    expect(await s.categories()).toEqual([
      ['restaurant.food', 'Restauración — comida (restaurant.food)'],
      ['product.generic', 'Producto — general (product.generic)'],
    ]);
    await ionValue(s.inDoc('tax-alias-form-category-search'), 'comida', 'ionInput');
    expect(s.params('tax.category.list')).toEqual([{ search: 'comida', sort: 'display_name', dir: 'asc', limit: 50 }]);
    await click(s.inDoc('tax-alias-form-category-close'));
    expect([s.field('source').value, s.options('source')]).toEqual([
      'learned',
      [
        ['learned', 'Learned'],
        ['shipped', 'Shipped'],
      ],
    ]);
  });

  it('waits for an alias and a category, then sends tax.alias.create and closes', async () => {
    const s = await setup();
    s.answer(201, { id: 'a1' });
    expect(s.add().disabled).toBe(true);
    await ionValue(s.field('alias'), ' Comida ', 'ionInput');
    await s.chooseCategory('restaurant.food');
    expect(s.add().disabled).toBe(false);
    await click(s.add());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/tax/aliases', query: {}, body: { alias: 'Comida', tax_category_key: 'restaurant.food', source: 'learned' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a repeated alias (409) is said under Alias and the dialog stays open', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'tax.alias_exists', message: 'That alias already exists.', fields: { alias: 'That alias already exists.' } } });
    await ionValue(s.field('alias'), 'comida', 'ionInput');
    await s.chooseCategory('restaurant.food');
    await ionValue(s.field('source'), 'shipped');
    await click(s.add());
    expect((s.sent()[0].body as { source: string }).source).toBe('shipped');
    expect(s.field('alias').errorText).toBe('That alias already exists.');
    expect(s.field('alias').classList.contains('ion-invalid')).toBe(true);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('tax-alias-form')?.getAttribute('aria-label')).toBe('Nuevo alias de categoría');
    expect([s.field('alias').placeholder, s.field('category').label, s.field('source').label]).toEqual(['comida', 'Categoría', 'Origen']);
    expect(s.options('source').map(([, label]) => label)).toEqual(['Aprendido', 'De fábrica']);
    expect(s.add().textContent?.trim()).toBe('Añadir');
  });
});

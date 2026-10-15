// THE tax-category picker of the sale app (a department's «VAT charged», SALE-F35; the till's open price
// later): a choice among the business's tax categories — any number of them — so it never loads them all:
// an outlined field, labelled by its host, that opens a modal with a searchbar over the live
// `tax.category.list` (50 at a time, searched on the server). Each choice reads «Name · rate» with the
// rate the server says it charges today. Under the field, the old notices: no category to choose («Set up
// your VAT first, in Taxes.») and a failed read («The tax categories could not be read.» with «Retry»).
import { describe, expect, it, vi } from 'vitest';

import { click, errorFrame, flush, ionValue, mountSale } from '../__tests__/mount-sale';
import { plain } from '../lib/format';
import TaxCategoryPicker from './TaxCategoryPicker.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'tax.category.list';
type Control = HTMLElement & { label?: string; value?: unknown; placeholder?: string; fill?: string; readonly?: boolean; errorText?: string; disabled?: boolean };

const category = (key: string, display_name: string, rate_pct: string | null) => ({
  id: key,
  key,
  name: key,
  description: '',
  display_name,
  display_description: '',
  is_system: true,
  is_active: true,
  rate_pct,
  operation_class: 'subject',
});
const PAGE = {
  rows: [category('general', 'General', '21.00'), category('restaurant.food', 'Restaurant — food', '10.00'), category('product.books', 'Books', null)],
  total: 3,
  limit: 50,
  offset: 0,
};

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const host = locale === 'es' ? { label: 'IVA que cobra', placeholder: 'Elige el IVA' } : { label: 'VAT charged', placeholder: 'Choose the VAT' };
  const m = await mountSale(TaxCategoryPicker, { props: { modelValue: '', testid: 'tax', ...host, ...props }, locale });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: string) => m.wrapper.setProps({ modelValue: value }) });
  await m.live();
  const field = () => m.inDoc('tax') as Control;
  const options = () => m.wrapper.findAll('[data-testid="tax-option"]').map((o) => [o.attributes('data-value'), plain(o.text().trim())]);
  const open = () => click(field());
  const search = async (text: string) => {
    await ionValue(m.inDoc('tax-search'), text, 'ionInput');
    await m.reopen();
  };
  const text = (id: string) => plain(m.inDoc(id)?.textContent?.trim() ?? '');
  return { ...m, field, options, open, search, text };
}

describe('TaxCategoryPicker: the field', () => {
  it('is an outlined md field, read-only, «VAT charged», with the name of what is chosen', async () => {
    const s = await setup({ modelValue: 'general', chosenLabel: 'General · 21%' });
    expect([s.field().tagName, s.field().label, s.field().fill, s.field().getAttribute('mode'), s.field().readonly, s.field().value]).toEqual([
      'ION-INPUT',
      'VAT charged',
      'outline',
      'md',
      true,
      'General · 21%',
    ]);
    expect((await setup()).field().placeholder).toBe('Choose the VAT');
  });

  it('is labelled by its host: the till names it otherwise', async () => {
    const s = await setup({ label: 'Tax', placeholder: 'Pick a tax' });
    await s.open();
    expect([s.field().label, s.field().placeholder, s.inDoc('tax-modal')?.getAttribute('aria-label')]).toEqual(['Tax', 'Pick a tax', 'Tax']);
  });

  it('says its error under it', async () => {
    const s = await setup({ errorText: 'Choose the VAT this department charges.' });
    expect(s.field().errorText).toBe('Choose the VAT this department charges.');
    expect(s.field().classList.contains('ion-invalid')).toBe(true);
  });
});

describe('TaxCategoryPicker: the choices, searched on the server', () => {
  it('follows tax.category.list 50 at a time, sorted by name, never the whole list', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'display_name', dir: 'asc', limit: 50 }]);
  });

  it('lists each category as «Name · rate today», the rate as the server says it', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    await s.open();
    expect(s.options()).toEqual([
      ['general', 'General · 21%'],
      ['restaurant.food', 'Restaurant — food · 10%'],
      ['product.books', 'Books'],
    ]);
  });

  it('a spinner until the first answer', async () => {
    const s = await setup();
    await s.open();
    expect(s.inDoc('tax-loading')).not.toBeNull();
    await s.result(OP, PAGE);
    expect(s.inDoc('tax-loading')).toBeNull();
  });

  it('searches the server with what is typed, trimmed', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    await s.open();
    await s.search('  rest ');
    expect(s.params(OP)).toEqual([{ search: 'rest', sort: 'display_name', dir: 'asc', limit: 50 }]);
    await s.result(OP, { ...PAGE, rows: [PAGE.rows[1]], total: 1 });
    expect(s.options()).toEqual([['restaurant.food', 'Restaurant — food · 10%']]);
  });

  it('nothing matches the search: says so', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    await s.open();
    await s.search('zzz');
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.text('tax-empty')).toBe('No tax category matches your search.');
    expect(s.inDoc('tax-none')).toBeNull();
  });

  it('more than it shows: asks to type to narrow the list', async () => {
    const s = await setup();
    await s.result(OP, { ...PAGE, total: 120 });
    await s.open();
    expect(s.text('tax-more')).toBe('Showing 3 of 120. Type to narrow the list.');
  });

  it('choosing one sets its key, closes the list and shows its name', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    await s.open();
    await click(s.wrapper.find('[data-testid="tax-option"][data-value="restaurant.food"]').element);
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['restaurant.food']);
    expect(s.inDoc('tax-search')).toBeNull();
    expect(plain(String(s.field().value))).toBe('Restaurant — food · 10%');
  });

  it('closes with its close button, choosing nothing', async () => {
    const s = await setup();
    await s.open();
    await click(s.inDoc('tax-close'));
    expect(s.inDoc('tax-search')).toBeNull();
    expect(s.wrapper.emitted('update:modelValue')).toBeUndefined();
  });
});

describe('TaxCategoryPicker: the old notices', () => {
  it('no category at all: «There are no tax categories to choose from. Set up your VAT first, in Taxes.»', async () => {
    const s = await setup();
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.text('tax-none')).toBe('There are no tax categories to choose from. Set up your VAT first, in Taxes.');
    // `v-model:empty`: the form keeps its submit off while there is nothing to choose.
    expect(s.wrapper.emitted('update:empty')?.at(-1)).toEqual([true]);
    await s.result(OP, PAGE, {}, 2);
    expect(s.wrapper.emitted('update:empty')?.at(-1)).toEqual([false]);
  });

  it('a failed read: «The tax categories could not be read.», the server’s words and «Retry» («Retrying…» meanwhile)', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'permission_denied'));
    await flush();
    const notice = s.text('tax-error');
    expect(notice).toContain('The tax categories could not be read.');
    expect(notice).toContain('msg permission_denied');
    const retry = () => s.inDoc('tax-retry') as Control;
    expect(retry().textContent?.trim()).toBe('Retry');
    await click(retry());
    expect([retry().textContent?.trim(), retry().disabled]).toEqual(['Retrying…', true]);
    await s.result(OP, PAGE);
    expect(s.inDoc('tax-error')).toBeNull();
  });

  it('speaks Spanish, with the rate as Spain writes it', async () => {
    const s = await setup({}, 'es');
    expect([s.field().label, s.field().placeholder]).toEqual(['IVA que cobra', 'Elige el IVA']);
    await s.result(OP, PAGE);
    await s.open();
    expect(s.options()[1]).toEqual(['restaurant.food', 'Restaurant — food · 10 %']);
    await s.search('zzz');
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.text('tax-empty')).toBe('Ninguna categoría de IVA coincide con tu búsqueda.');
  });
});

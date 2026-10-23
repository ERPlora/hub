// «Categories» of the product form (WORKBOOK INVENTORY-F01, INVENTORY-F08), as Shopify's «Collections»
// and Odoo's tags: a `Combo` of @erplora/ui that searches the business's categories on the server (at
// most 100 per query) to add one more, and the chosen ones under it as chips, each removed with its
// button. The field is only there when the business has categories (the first page, followed live,
// also names the chosen ones); a category is never added twice nor offered once chosen.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import {
  category,
  errorFrame,
  flush,
  mountInventory,
  type MountOptions,
  ok,
  page,
  refusal,
  subId,
} from '../__tests__/mount-inventory';
import ProductCategoriesField from './ProductCategoriesField.vue';

const CATEGORIES = page([category(), category({ id: 'c2', name: 'Food', slug: 'food' })], 2, 100);

async function setup(modelValue: string[] = [], options: MountOptions & { first?: unknown } = {}) {
  const m = await mountInventory(ProductCategoriesField, {
    props: { modelValue, testid: 'cat' },
    api: () => ok(CATEGORIES),
    ...options,
  });
  const call = await m.live();
  await m.result(call, 'inventory.category.list', options.first ?? CATEGORIES);
  const combo = () => m.wrapper.findComponent(Combo);
  async function offers(query = '') {
    const found = await (combo().props('search') as (q: string) => Promise<ComboOption[]>)(query);
    await flush();
    return found.map((o) => [o.id, o.label]);
  }
  async function choose(option: ComboOption) {
    combo().vm.$emit('update:modelValue', option);
    await flush();
  }
  // happy-dom reads no text through Ionic's shadow elements (ion-chip): a chip's name is its span.
  const chips = () => m.wrapper.findAll('[data-testid^="cat-chip-"] span').map((c) => c.text());
  const searches = () => m.calls('/api/inventory/categories').map((c) => m.query(c));
  const last = () => m.wrapper.emitted('update:modelValue')?.at(-1);
  return { ...m, call, combo, offers, choose, chips, searches, last };
}

describe('ProductCategoriesField', () => {
  it('follows the first page of the categories live, by name', async () => {
    const s = await setup();
    expect(s.params('inventory.category.list')).toEqual([{ limit: 100, sort: 'name' }]);
  });

  it('is a Combo «Categories» searching the server, at most 100 per query', async () => {
    const s = await setup();
    expect([s.combo().props('label'), s.combo().props('placeholder'), s.combo().props('testid')]).toEqual([
      'Categories',
      'Search a category to add',
      'cat',
    ]);
    expect(await s.offers()).toEqual([
      ['c1', 'Drinks'],
      ['c2', 'Food'],
    ]);
    expect(s.searches()).toEqual([{ limit: '100', sort: 'name' }]);
    await s.offers(' fo ');
    expect(s.searches().at(-1)).toEqual({ limit: '100', sort: 'name', search: 'fo' });
  });

  it('shows the chosen categories by name as chips, and does not offer them again', async () => {
    const s = await setup(['c1']);
    expect(s.chips()).toEqual(['Drinks']);
    expect(await s.offers()).toEqual([['c2', 'Food']]);
  });

  it('adds a picked category after the chosen ones and empties the field for the next one', async () => {
    const s = await setup(['c1']);
    await s.choose({ id: 'c2', label: 'Food' });
    expect(s.last()).toEqual([['c1', 'c2']]);
    expect(s.combo().props('modelValue')).toBeNull();
  });

  it('never adds a category twice', async () => {
    const s = await setup(['c1']);
    await s.choose({ id: 'c1', label: 'Drinks' });
    expect(s.wrapper.emitted('update:modelValue')).toBeUndefined();
  });

  it('removes a chosen category with the button of its chip', async () => {
    const s = await setup(['c1', 'c2']);
    const remove = s.wrapper.find('[aria-label="Remove Drinks"]');
    expect(remove.attributes('data-testid')).toBe('cat-remove-c1');
    (remove.element as HTMLElement).click();
    await flush();
    expect(s.last()).toEqual([['c2']]);
  });

  it('keeps the name of a category found by a search beyond the first page', async () => {
    const wines = category({ id: 'c9', name: 'Wines', slug: 'wines' });
    const s = await setup([], { first: page([category()], 140, 100), api: () => ok(page([wines])) });
    await s.offers('win');
    await s.choose({ id: 'c9', label: 'Wines' });
    await s.wrapper.setProps({ modelValue: ['c9'] });
    expect(s.chips()).toEqual(['Wines']);
    // Its name came with the pick: nothing is asked for it.
    expect(s.searches().filter((q) => 'ids' in q)).toEqual([]);
  });

  it('names the chosen categories beyond the first page at opening, asking only for those', async () => {
    const wines = category({ id: 'c9', name: 'Wines', slug: 'wines' });
    const s = await setup(['c1', 'c9', 'c8'], {
      first: page([category()], 140, 100),
      api: () => ok(page([wines, category({ id: 'c8', name: 'Beers', slug: 'beers' })])),
    });
    const asked = s.calls('/api/inventory/categories').map((c) => new URL(c.url, 'http://a.localhost').searchParams);
    expect(asked.map((q) => [q.getAll('ids'), q.get('limit'), q.get('sort')])).toEqual([[['c9', 'c8'], '100', 'name']]);
    expect(s.chips()).toEqual(['Drinks', 'Wines', 'Beers']);
  });

  it('a chosen category the server no longer lists shows a dash, not «Loading…»', async () => {
    const s = await setup(['c9'], { first: page([category()], 140, 100), api: () => ok(page([])) });
    expect(s.chips()).toEqual(['—']);
  });

  it('asks nothing more when the first page names every chosen category', async () => {
    const s = await setup(['c1', 'c2']);
    expect(s.searches()).toEqual([]);
  });

  it('with every category on the first page, asks nothing for a chosen one it lacks (it no longer exists)', async () => {
    const s = await setup(['c1', 'c9']);
    expect(s.searches()).toEqual([]);
    expect(s.chips()).toEqual(['Drinks', '—']);
  });

  it('says «Loading…» on a chip while it names its category', async () => {
    const s = await setup(['c9'], { first: page([category()], 140, 100), api: () => new Promise<Response>(() => {}) });
    expect(s.chips()).toEqual(['Loading…']);
  });

  it('says when the chosen categories could not be named, with the reason', async () => {
    const s = await setup(['c9'], { first: page([category()], 140, 100), api: () => refusal(503, 'unavailable', 'Try again later.') });
    const error = s.wrapper.find('[data-testid="cat-error"]');
    expect(error.text()).toContain('The categories could not be loaded');
    expect(error.text()).toContain('Try again later.');
  });

  it('is not there while the business has no categories', async () => {
    const s = await setup([], { first: page([], 0, 100) });
    expect(s.combo().exists()).toBe(false);
    expect(s.wrapper.find('[data-testid="cat-error"]').exists()).toBe(false);
  });

  it('says when the categories could not be loaded, with the reason', async () => {
    const m = await mountInventory(ProductCategoriesField, { props: { modelValue: [], testid: 'cat' } });
    const call = await m.live();
    call.push(errorFrame(subId(m.client, 'inventory.category.list'), 'permission_denied'));
    await flush();
    const error = m.wrapper.find('[data-testid="cat-error"]');
    expect(error.text()).toContain('The categories could not be loaded');
    expect(error.text()).toContain('msg permission_denied');
  });

  it('paints the error the server gave the field', async () => {
    const s = await setup();
    await s.wrapper.setProps({ errorText: 'That category does not exist.' });
    expect(s.combo().props('errorText')).toBe('That category does not exist.');
  });

  it('typing a name and Enter adds the first match', async () => {
    const s = await setup([], { attach: true });
    const field = document.querySelector('ion-input[data-testid="cat"]') as HTMLElement & { value?: string };
    field.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Dri' } }));
    await new Promise((resolve) => setTimeout(resolve, 200));
    await flush();
    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await flush();
    expect(s.last()).toEqual([['c1']]);
    expect(field.value).toBe('');
    s.wrapper.unmount();
  });

  it('speaks Spanish', async () => {
    const s = await setup(['c1'], { locale: 'es' });
    expect([s.combo().props('label'), s.combo().props('placeholder')]).toEqual(['Categorías', 'Busca una categoría para añadirla']);
    expect(s.wrapper.find('[aria-label="Quitar Drinks"]').exists()).toBe(true);
  });
});

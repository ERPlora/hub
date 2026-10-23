// The tax category picker of a product and of a category (WORKBOOK «La categoría fiscal se elige por
// su tipo»): a `Combo` of @erplora/ui that searches Taxes' `tax.category.list` on the server (at most
// 100 per query) and offers each category by its name and its rate («Product — generic · 21 %», «… ·
// exempt», the bare name without a rule), never its technical key and never one chosen in advance. It
// also follows the first page live, for the name of the chosen category, «Not configured · Missing
// tax category» (a product with none, or one Taxes deactivated), «no categories at all» and the
// loading error. A category's picker offers «— (default)», an empty key.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import {
  errorFrame,
  flush,
  mountInventory,
  type MountOptions,
  ok,
  page,
  refusal,
  subId,
  TAX_CATEGORIES,
} from '../__tests__/mount-inventory';
import TaxCategorySelect from './TaxCategorySelect.vue';

async function setup(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountInventory(TaxCategorySelect, {
    props: { modelValue: '', testid: 'tax', ...props },
    api: () => ok(TAX_CATEGORIES),
    ...options,
  });
  const call = await m.live();
  const show = (data: unknown) => m.result(call, 'tax.category.list', data);
  const combo = () => m.wrapper.findComponent(Combo);
  /** What the field offers for `query` (`''`: on opening), as [key, label]. */
  async function offers(query = '') {
    const found = await (combo().props('search') as (q: string) => Promise<ComboOption[]>)(query);
    await flush();
    return found.map((o) => [o.id, o.label]);
  }
  /** The person picks `option` in the field. */
  async function choose(option: ComboOption | null) {
    combo().vm.$emit('update:modelValue', option);
    await flush();
  }
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  // happy-dom reads no text through Ionic's shadow elements (ion-chip): the marker's text is its span.
  const marker = () => testid('tax-unconfigured').find('span').text();
  const searches = () => m.calls('/api/tax/categories').map((c) => m.query(c));
  return { ...m, call, show, combo, offers, choose, testid, marker, searches };
}

describe('TaxCategorySelect', () => {
  it('follows the first page of tax.category.list live, sorted by the name the reader reads', async () => {
    const s = await setup();
    expect(s.params('tax.category.list')).toEqual([{ limit: 100, sort: 'display_name' }]);
  });

  it('is a Combo searching Taxes on the server, at most 100 per query, each category by its name and rate', async () => {
    const s = await setup();
    await s.show(TAX_CATEGORIES);
    expect(await s.offers()).toEqual([
      ['product.generic', 'Product — generic · 21%'],
      ['service.health', 'Service — healthcare (VAT exempt) · exempt'],
      ['shop.own', 'Own category'],
    ]);
    expect(s.searches()).toEqual([{ limit: '100', sort: 'display_name' }]);
    await s.offers('  alco ');
    expect(s.searches().at(-1)).toEqual({ limit: '100', sort: 'display_name', search: 'alco' });
  });

  it("offers a factory category by the name Taxes translates for the reader, never the stored one (taxes#38)", async () => {
    const [generic] = TAX_CATEGORIES.rows;
    const s = await setup({}, { api: () => ok(page([{ ...generic, display_name: 'Producto — general' }])) });
    expect(await s.offers()).toEqual([['product.generic', 'Producto — general · 21%']]);
  });

  it('has its label and placeholder, nothing chosen in advance and no way to empty a required field', async () => {
    const s = await setup();
    await s.show(TAX_CATEGORIES);
    const combo = s.combo();
    expect([combo.props('label'), combo.props('placeholder'), combo.props('testid'), combo.props('clearable')]).toEqual([
      'Tax category',
      'Pick a tax category',
      'tax',
      false,
    ]);
    expect(combo.props('modelValue')).toBeNull();
  });

  it('shows the chosen category by its name and rate', async () => {
    const s = await setup({ modelValue: 'product.generic' });
    await s.show(TAX_CATEGORIES);
    expect(s.combo().props('modelValue')).toEqual({ id: 'product.generic', label: 'Product — generic · 21%' });
  });

  it('hands the parent the key that was picked, once', async () => {
    const s = await setup();
    await s.show(TAX_CATEGORIES);
    await s.choose({ id: 'service.health', label: 'Service — healthcare (VAT exempt) · exempt' });
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['service.health']]);
    await s.wrapper.setProps({ modelValue: 'service.health' });
    await s.choose({ id: 'service.health', label: 'Service — healthcare (VAT exempt) · exempt' });
    expect(s.wrapper.emitted('update:modelValue')).toHaveLength(1);
  });

  it('keeps the name of a category found by a search beyond the first page', async () => {
    const wine = { ...TAX_CATEGORIES.rows[0], id: 't9', key: 'drink.wine', name: 'Wine', display_name: 'Wine', rate_pct: '10.00' };
    const s = await setup({}, { api: () => ok(page([wine])) });
    await s.show({ ...TAX_CATEGORIES, total: 140 });
    const [[key, label]] = await s.offers('wine');
    await s.choose({ id: key!, label: label! });
    await s.wrapper.setProps({ modelValue: 'drink.wine' });
    expect(s.combo().props('modelValue')).toEqual({ id: 'drink.wine', label: 'Wine · 10%' });
  });

  it('marks «Not configured» when asked and the value is empty or no longer an active category', async () => {
    const s = await setup({ modelValue: 'old.deactivated', markMissing: true });
    await s.show(TAX_CATEGORIES);
    expect(s.marker()).toBe('Not configured · Missing tax category');
    // A deactivated category is not offered, so the field shows none.
    expect(s.combo().props('modelValue')).toBeNull();
    await s.wrapper.setProps({ modelValue: 'product.generic' });
    expect(s.testid('tax-unconfigured').exists()).toBe(false);
    await s.wrapper.setProps({ modelValue: '' });
    expect(s.testid('tax-unconfigured').exists()).toBe(true);
  });

  it('does not mark anything before the categories arrive, nor without being asked', async () => {
    const s = await setup({ modelValue: '' });
    expect(s.testid('tax-unconfigured').exists()).toBe(false);
    await s.show(TAX_CATEGORIES);
    expect(s.testid('tax-unconfigured').exists()).toBe(false);
  });

  // Beyond the first page (more categories than one query holds), the chosen one is named by asking
  // Taxes for its key: by its name and rate, never its key; one Taxes no longer lists is «Not configured».
  const WINE = { ...TAX_CATEGORIES.rows[0], id: 't9', key: 'drink.wine', name: 'Wine', display_name: 'Wine', rate_pct: '10.00' };
  const SPARKLING = { ...WINE, id: 't10', key: 'drink.wine.sparkling', name: 'Sparkling wine', display_name: 'Sparkling wine' };

  it('names a chosen category beyond the first page by asking Taxes for its key, by its name and rate', async () => {
    // The list filters by part of the key: the exact one is kept, wherever it comes.
    const s = await setup({ modelValue: 'drink.wine', markMissing: true }, { api: () => ok(page([SPARKLING, WINE])) });
    await s.show({ ...TAX_CATEGORIES, total: 140 });
    expect(s.searches()).toEqual([{ limit: '100', sort: 'display_name', key: 'drink.wine' }]);
    expect(s.combo().props('modelValue')).toEqual({ id: 'drink.wine', label: 'Wine · 10%' });
    expect(s.testid('tax-unconfigured').exists()).toBe(false);
  });

  it('asks nothing more when the first page names the chosen category', async () => {
    const s = await setup({ modelValue: 'product.generic' });
    await s.show({ ...TAX_CATEGORIES, total: 140 });
    await s.show(TAX_CATEGORIES);
    expect(s.searches()).toEqual([]);
  });

  it('says «Loading…» in the field while it names the chosen category', async () => {
    const s = await setup({ modelValue: 'drink.wine' }, { api: () => new Promise<Response>(() => {}) });
    await s.show({ ...TAX_CATEGORIES, total: 140 });
    expect(s.combo().props('modelValue')).toEqual({ id: 'drink.wine', label: 'Loading…' });
  });

  it('a chosen category beyond the first page that Taxes no longer lists is «Not configured» and shows none', async () => {
    const s = await setup({ modelValue: 'old.deactivated', markMissing: true }, { api: () => ok(page([])) });
    await s.show({ ...TAX_CATEGORIES, total: 140 });
    expect(s.combo().props('modelValue')).toBeNull();
    expect(s.marker()).toBe('Not configured · Missing tax category');
  });

  it('says when the chosen category could not be named, with the reason', async () => {
    const s = await setup({ modelValue: 'drink.wine' }, { api: () => refusal(503, 'unavailable', 'Try again later.') });
    await s.show({ ...TAX_CATEGORIES, total: 140 });
    expect(s.testid('tax-error').text()).toContain('The tax categories could not be loaded');
    expect(s.testid('tax-error').text()).toContain('Try again later.');
  });

  it('with more categories than one query holds, marks an empty value', async () => {
    const s = await setup({ modelValue: '', markMissing: true });
    await s.show({ ...TAX_CATEGORIES, total: 140 });
    expect(s.testid('tax-unconfigured').exists()).toBe(true);
  });

  it('offers «— (default)» first on a category, which hands back an empty key, and shows it when chosen', async () => {
    const s = await setup({ allowDefault: true, label: 'Tax rate' });
    await s.show(TAX_CATEGORIES);
    expect((await s.offers())[0]).toEqual(['', '— (default)']);
    expect((await s.offers('prod'))[0]).toEqual(['product.generic', 'Product — generic · 21%']);
    expect(s.combo().props('label')).toBe('Tax rate');
    expect(s.combo().props('modelValue')).toEqual({ id: '', label: '— (default)' });
    await s.wrapper.setProps({ modelValue: 'product.generic' });
    await s.choose({ id: '', label: '— (default)' });
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['']]);
  });

  it('without any category says to create them in Taxes', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.testid('tax-none').text()).toBe(
      'There are no tax categories yet. Create them in Taxes: a product cannot be sold until it is known how it is taxed.',
    );
  });

  it('a category picker without categories still offers the default, and says nothing', async () => {
    const s = await setup({ allowDefault: true }, { api: () => ok(page([])) });
    await s.show(page([]));
    expect(s.testid('tax-none').exists()).toBe(false);
    expect(await s.offers()).toEqual([['', '— (default)']]);
  });

  it('says when the categories could not be loaded, with the reason', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'tax.category.list'), 'permission_denied'));
    await flush();
    expect(s.testid('tax-error').text()).toContain('The tax categories could not be loaded');
    expect(s.testid('tax-error').text()).toContain('msg permission_denied');
  });

  it('a search the server refuses fails, so the field says so and offers to retry', async () => {
    const s = await setup({}, { api: () => refusal(503, 'unavailable', 'Try again later.') });
    await expect(s.offers('wine')).rejects.toThrow('Try again later.');
    expect(s.searches()).toEqual([{ limit: '100', sort: 'display_name', search: 'wine' }]);
  });

  it('paints the error the server gave the field', async () => {
    const s = await setup({ errorText: 'This tax category does not exist in Taxes.' });
    await s.show(TAX_CATEGORIES);
    expect(s.combo().props('errorText')).toBe('This tax category does not exist in Taxes.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ markMissing: true }, { locale: 'es' });
    await s.show(TAX_CATEGORIES);
    expect((await s.offers())[1]).toEqual(['service.health', 'Service — healthcare (VAT exempt) · exento']);
    expect(s.combo().props('placeholder')).toBe('Elige una categoría fiscal');
    expect(s.marker()).toBe('Sin configurar · Falta la categoría fiscal');
  });
});

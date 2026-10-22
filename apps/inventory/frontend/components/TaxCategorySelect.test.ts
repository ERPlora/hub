// The tax category picker of a product and of a category (WORKBOOK «La categoría fiscal se elige por
// su tipo»): it follows Taxes' `tax.category.list` live and offers each category by its name and its
// rate («Product — generic · 21 %», «… · exempt», the bare name without a rule), never its technical
// key and never one chosen in advance. A product's picker has no empty option (the tax category is
// required) and marks «Not configured · Missing tax category» when the product has none or Taxes
// deactivated it; a category's picker offers «— (default)». No categories at all says where to make them.
import { IonSelect } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountInventory, type MountOptions, page, subId, TAX_CATEGORIES } from '../__tests__/mount-inventory';
import SearchSelect from './SearchSelect.vue';
import TaxCategorySelect from './TaxCategorySelect.vue';

type Control = HTMLElement & { value?: unknown; placeholder?: string; errorText?: string };

async function setup(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountInventory(TaxCategorySelect, {
    props: { modelValue: '', testid: 'tax', ...props },
    ...options,
  });
  const call = await m.live();
  const show = (data: unknown) => m.result(call, 'tax.category.list', data);
  const select = () => m.wrapper.findComponent(IonSelect);
  const options_ = () => m.wrapper.findAll('ion-select-option').map((o) => [(o.element as Control).value, o.text()]);
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  // happy-dom reads no text through Ionic's shadow elements (ion-chip): the marker's text is its span.
  const marker = () => testid('tax-unconfigured').find('span').text();
  return { ...m, call, show, select, options: options_, testid, marker };
}

describe('TaxCategorySelect', () => {
  it('follows tax.category.list: the active categories by the name the reader reads', async () => {
    const s = await setup();
    expect(s.params('tax.category.list')).toEqual([{ limit: 100, sort: 'display_name' }]);
    await s.show(TAX_CATEGORIES);
    expect(s.options()).toEqual([
      ['product.generic', 'Product — generic · 21%'],
      ['service.health', 'Service — healthcare (VAT exempt) · exempt'],
      ['shop.own', 'Own category'],
    ]);
  });

  it("offers a factory category by the name Taxes translates for the reader, never the stored one (taxes#38)", async () => {
    const s = await setup();
    const [generic] = TAX_CATEGORIES.rows;
    await s.show(page([{ ...generic, display_name: 'Producto — general' }]));
    expect(s.options()).toEqual([['product.generic', 'Producto — general · 21%']]);
  });

  it('is an outlined md select with its label and placeholder, nothing chosen in advance', async () => {
    const s = await setup();
    await s.show(TAX_CATEGORIES);
    const select = s.select();
    expect([select.props('fill'), select.attributes('mode'), select.props('label'), select.props('placeholder')]).toEqual([
      'outline',
      'md',
      'Tax category',
      'Pick a tax category',
    ]);
    expect((select.element as Control).value).toBe('');
    expect(select.attributes('data-testid')).toBe('tax');
  });

  it('hands the parent the key that was picked', async () => {
    const s = await setup();
    await s.show(TAX_CATEGORIES);
    await s.select().setValue('service.health');
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['service.health']]);
  });

  it('marks «Not configured» when asked and the value is empty or no longer an active category', async () => {
    const s = await setup({ modelValue: 'old.deactivated', markMissing: true });
    await s.show(TAX_CATEGORIES);
    expect(s.marker()).toBe('Not configured · Missing tax category');
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

  it('offers «— (default)» first on a category, which hands back an empty key', async () => {
    const s = await setup({ allowDefault: true, label: 'Tax rate' });
    await s.show(TAX_CATEGORIES);
    expect(s.options()[0]).toEqual(['', '— (default)']);
    expect(s.select().props('label')).toBe('Tax rate');
  });

  it('without any category says to create them in Taxes', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.testid('tax-none').text()).toBe(
      'There are no tax categories yet. Create them in Taxes: a product cannot be sold until it is known how it is taxed.',
    );
  });

  it('a category picker without categories still offers the default, and says nothing', async () => {
    const s = await setup({ allowDefault: true });
    await s.show(page([]));
    expect(s.testid('tax-none').exists()).toBe(false);
    expect(s.options()).toEqual([['', '— (default)']]);
  });

  it('says when the categories could not be loaded, with the reason', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'tax.category.list'), 'permission_denied'));
    await flush();
    expect(s.testid('tax-error').text()).toContain('The tax categories could not be loaded');
    expect(s.testid('tax-error').text()).toContain('msg permission_denied');
  });

  it('paints the error the server gave the field', async () => {
    const s = await setup({ errorText: 'This tax category does not exist in Taxes.' });
    await s.show(TAX_CATEGORIES);
    expect((s.select().element as Control).errorText).toBe('This tax category does not exist in Taxes.');
    expect(s.select().classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
  });

  it('a business with more categories than one query serves searches them on the server', async () => {
    const s = await setup({ modelValue: 'product.generic' });
    await s.show({ ...TAX_CATEGORIES, total: 140 });
    expect(s.select().exists()).toBe(false);
    const field = s.wrapper.findComponent(SearchSelect);
    expect([field.props('complete'), field.props('modelValue')]).toEqual([false, 'product.generic']);
    field.vm.$emit('update:search', 'alco');
    await flush();
    expect(s.params('tax.category.list')).toEqual([{ limit: 100, sort: 'display_name', search: 'alco' }]);
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'tax.category.list', page([], 0, 100));
    expect(s.wrapper.findComponent(SearchSelect).props('complete')).toBe(false);
    expect(s.testid('tax-none').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ markMissing: true }, { locale: 'es' });
    await s.show(TAX_CATEGORIES);
    expect(s.options()[1]).toEqual(['service.health', 'Service — healthcare (VAT exempt) · exento']);
    expect(s.select().props('placeholder')).toBe('Elige una categoría fiscal');
    expect(s.marker()).toBe('Sin configurar · Falta la categoría fiscal');
  });
});

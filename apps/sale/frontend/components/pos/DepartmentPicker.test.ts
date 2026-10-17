// «Section (VAT)» of the open price (SALE-F09, F35): the business's sections, each with the rate
// it charges today, searched on the server; without sections, Taxes' categories through the app's one
// tax-category picker (which says it when there is none either).
import { describe, expect, it } from 'vitest';
import { h, ref } from 'vue';

import { click, errorFrame, ionValue, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { page } from './__tests__/fixtures';
import DepartmentPicker, { type OpenPriceChoice } from './DepartmentPicker.vue';
import TaxCategoryPicker from '../TaxCategoryPicker.vue';

const DEPARTMENTS = 'sale.department.list';

const department = (id: string, name: string, rate: string | null = '21.00') => ({
  id,
  name,
  tax_category_key: 'general',
  tax_category_name: 'General',
  tax_rate_pct: rate,
  sort_order: 0,
});

async function setup(locale: 'en' | 'es' = 'en') {
  const choice = ref<OpenPriceChoice | null>(null);
  const m = await mountSale(
    { setup: () => () => h(DepartmentPicker, { modelValue: choice.value, 'onUpdate:modelValue': (v: OpenPriceChoice | null) => (choice.value = v) }) },
    { locale },
  );
  await m.live();
  return { ...m, choice };
}

describe('DepartmentPicker', () => {
  it('asks the departments in their order, 20 at a time, and searches on the server', async () => {
    const m = await setup();
    expect(m.params(DEPARTMENTS)).toEqual([{ search: '', sort: 'sort_order', dir: 'asc', limit: 20, offset: 0 }]);
    await m.result(DEPARTMENTS, page([department('d1', 'Fruit')]));
    await ionValue(m.wrapper.find('ion-searchbar').element, 'fru', 'ionInput');
    await m.reopen();
    expect(m.params(DEPARTMENTS)).toEqual([{ search: 'fru', sort: 'sort_order', dir: 'asc', limit: 20, offset: 0 }]);
  });

  it('paints each department with its rate; a tap chooses it', async () => {
    const m = await setup('es');
    await m.result(DEPARTMENTS, page([department('d1', 'Frutas', '4.00'), department('d2', 'Droguería', null)]));
    const fruit = m.find('pos-department-d1');
    expect(fruit.find('.pos-choice__name').text()).toBe('Frutas');
    expect(plain(fruit.find('.pos-choice__rate').text())).toBe('4 %');
    expect(m.find('pos-department-d2').find('.pos-choice__rate').exists()).toBe(false);
    await click(fruit.element);
    expect(m.choice.value).toEqual({ kind: 'department', id: 'd1' });
    expect(m.find('pos-department-d1').attributes('aria-pressed')).toBe('true');
  });

  it('without departments it offers Taxes’ categories instead, through the app’s tax-category picker', async () => {
    const m = await setup();
    await m.result(DEPARTMENTS, page([]));
    const picker = m.wrapper.findComponent(TaxCategoryPicker);
    expect(picker.props()).toMatchObject({ label: 'Section (VAT)', testid: 'pos-tax-category', modelValue: '' });
    picker.vm.$emit('update:modelValue', 'food');
    await m.wrapper.vm.$nextTick();
    expect(m.choice.value).toEqual({ kind: 'tax', key: 'food' });
  });

  it('in Ceuta or Melilla the categories’ picker is «Section (IPSI)»', async () => {
    const m = await setup();
    await m.result('sale.sale.tax_kind', { tax: 'ipsi' });
    await m.result(DEPARTMENTS, page([]));
    expect(m.wrapper.findComponent(TaxCategoryPicker).props()).toMatchObject({ label: 'Section (IPSI)' });
  });

  it('a search that finds no department is not the same as having none', async () => {
    const m = await setup();
    await m.result(DEPARTMENTS, page([department('d1', 'Fruit')]));
    await ionValue(m.wrapper.find('ion-searchbar').element, 'zzz', 'ionInput');
    await m.reopen();
    await m.result(DEPARTMENTS, page([]));
    expect(m.wrapper.findComponent(TaxCategoryPicker).exists()).toBe(false);
    expect(m.find('pos-departments-none').text()).toBe('No section matches your search.');
  });

  it('says it when the departments cannot be read', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId(DEPARTMENTS), 'internal_error'));
    await m.reopen();
    expect(m.find('pos-departments-error').text()).toBe('The sections could not be loaded.');
  });
});

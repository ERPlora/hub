// The open price's fallback when the business has no departments (SALE-F09): Taxes' active categories
// with today's rate, searched on the server; with none, «No departments configured.».
import { describe, expect, it } from 'vitest';
import { h, ref } from 'vue';

import { click, ionValue, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { page } from './__tests__/fixtures';
import type { OpenPriceChoice } from './DepartmentPicker.vue';
import TaxCategoryPicker from './TaxCategoryPicker.vue';

const OP = 'tax.category.list';

const category = (key: string, name: string, over: Record<string, unknown> = {}) => ({
  id: key,
  key,
  name,
  description: '',
  display_name: name,
  display_description: '',
  is_system: true,
  is_active: true,
  rate_pct: '10.00',
  operation_class: 'subject',
  ...over,
});

async function setup(locale: 'en' | 'es' = 'en') {
  const choice = ref<OpenPriceChoice | null>(null);
  const m = await mountSale(
    { setup: () => () => h(TaxCategoryPicker, { modelValue: choice.value, 'onUpdate:modelValue': (v: OpenPriceChoice | null) => (choice.value = v) }) },
    { locale },
  );
  await m.live();
  return { ...m, choice };
}

describe('TaxCategoryPicker', () => {
  it('asks the categories by name, 20 at a time, and searches on the server', async () => {
    const m = await setup();
    expect(m.params(OP)).toEqual([{ search: '', sort: 'display_name', dir: 'asc', limit: 20, offset: 0 }]);
    await ionValue(m.wrapper.find('ion-searchbar').element, 'food', 'ionInput');
    await m.reopen();
    expect(m.params(OP)[0].search).toBe('food');
  });

  it('offers the active ones with today’s rate; a tap chooses it by key', async () => {
    const m = await setup('es');
    await m.result(OP, page([category('food', 'Alimentación'), category('old', 'Antigua', { is_active: false })]));
    expect(m.find('pos-tax-category-old').exists()).toBe(false);
    const food = m.find('pos-tax-category-food');
    expect(plain(food.find('.pos-choice__rate').text())).toBe('10 %');
    await click(food.element);
    expect(m.choice.value).toEqual({ kind: 'tax', key: 'food', name: 'Alimentación' });
  });

  it('with none, «No departments configured.»', async () => {
    const m = await setup();
    await m.result(OP, page([]));
    expect(m.find('pos-tax-categories-none').text()).toBe('No departments configured.');
  });
});

import { InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { mountSale, settle } from '../../__tests__/mount-sale';
import { line } from './__tests__/fixtures';
import CartLineDetails from './CartLineDetails.vue';

const MENU_DISH = {
  option_id: 'burger',
  group_name: 'Mains',
  product_id: 'burger',
  product_name: 'Burger',
  category_id: null,
  is_service: false,
  quantity: 1,
  price_delta: 0,
  tax_category_key: null,
  amount: null,
  modifiers: [],
};

async function setup(over: Parameters<typeof line>[0] = {}) {
  const m = await mountSale(CartLineDetails, { props: { line: line(over) }, locale: 'es' });
  await settle();
  return m;
}

describe('CartLineDetails', () => {
  it('uses text and an icon for the allergy warning, not colour alone', async () => {
    const m = await setup({ allergens: ['gluten'], allergy: ['gluten'], allergy_in_dish: ['gluten'] });
    expect(m.find('pos-line-l1-allergy').text()).toContain('Alergia: Gluten');
    expect(m.find('pos-line-l1-allergy-match').text()).toBe('El plato lleva Gluten');
    expect(m.find('pos-line-l1-allergy').find('ion-icon').exists()).toBe(true);
  });

  it('raises the warning to danger only when the dish, or a dish of the menu, carries the allergy', async () => {
    const tone = async (over: Parameters<typeof line>[0]) => (await setup(over)).wrapper.findComponent(InlineFeedback).props('tone');
    const dish = { ...MENU_DISH, allergens: ['milk' as const], allergy_in_dish: ['milk' as const] };
    const menu = { combo_id: 'm1', kitchen_name: 'MENU', supply_kind: 'service' as const, split: false, components: [dish] };
    expect(await tone({ allergy: ['gluten'], allergy_in_dish: [] })).toBe('warning');
    expect(await tone({ allergy: ['gluten'], allergy_in_dish: ['gluten'] })).toBe('danger');
    expect(await tone({ product_id: null, allergy: ['milk'], allergy_in_dish: [], combo: menu })).toBe('danger');
  });

  it('names the options of each dish of a menu with the dish (SALE-F42)', async () => {
    const steak = { ...MENU_DISH, option_id: 'steak', product_name: 'Entrecot', modifiers: ['Poco hecho', 'Queso'], allergens: [], allergy_in_dish: [] };
    const fries = { ...MENU_DISH, option_id: 'fries', product_name: 'Patatas', allergens: [], allergy_in_dish: [] };
    const menu = { combo_id: 'm1', kitchen_name: 'MENU', supply_kind: 'service' as const, split: false, components: [fries, steak] };
    const m = await setup({ product_id: null, combo: menu });
    expect(m.find('pos-line-l1-dishes').text()).toBe('Patatas, Entrecot (Poco hecho, Queso)');
  });

  it('renders neither allergen nor allergy rows for a plain line', async () => {
    const m = await setup({ allergens: [], allergy: [], allergy_in_dish: [] });
    expect(m.find('pos-line-l1-allergens').exists()).toBe(false);
    expect(m.find('pos-line-l1-allergy').exists()).toBe(false);
  });
});

import { describe, expect, it } from 'vitest';

import { mountSale, settle } from '../../__tests__/mount-sale';
import { line } from './__tests__/fixtures';
import CartLineDetails from './CartLineDetails.vue';

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

  it('renders neither allergen nor allergy rows for a plain line', async () => {
    const m = await setup({ allergens: [], allergy: [], allergy_in_dish: [] });
    expect(m.find('pos-line-l1-allergens').exists()).toBe(false);
    expect(m.find('pos-line-l1-allergy').exists()).toBe(false);
  });
});

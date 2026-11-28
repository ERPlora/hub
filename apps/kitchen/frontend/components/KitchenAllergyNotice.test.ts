import { describe, expect, it } from 'vitest';

import { item } from '../__tests__/kitchen';
import { mountKitchen } from '../__tests__/mount-kitchen';
import type { ItemOut } from '../operations/tickets';
import KitchenAllergyNotice from './KitchenAllergyNotice.vue';

async function setup(line: ItemOut, locale: 'en' | 'es' = 'en') {
  return mountKitchen(KitchenAllergyNotice, { props: { line, testid: 'dish-allergy' }, locale });
}

describe('KitchenAllergyNotice', () => {
  it('renders nothing when the dish has no allergy', async () => {
    const m = await setup(item('i1', { allergy: [], allergy_in_dish: [] }));
    expect(m.find('dish-allergy').exists()).toBe(false);
  });

  it('names the allergy and, apart, what of it the dish contains', async () => {
    const m = await setup(item('i1', {
      allergy: ['gluten', 'milk'],
      allergy_in_dish: ['milk'],
    }));
    expect(m.find('dish-allergy').text()).toContain('Allergy: Gluten, Milk');
    expect(m.find('dish-allergy-contains').text()).toBe('The dish contains Milk');
  });

  it('says only the allergy when the dish contains none of it', async () => {
    const m = await setup(item('i1', { allergy: ['peanut'], allergy_in_dish: [] }));
    expect(m.find('dish-allergy').text()).toBe('Allergy: Peanut');
    expect(m.find('dish-allergy-contains').exists()).toBe(false);
  });

  it('uses the names of the shared list of fourteen, the ones the till and the paper use', async () => {
    const m = await setup(item('i1', {
      allergy: ['tree_nuts', 'lupin'],
      allergy_in_dish: ['lupin'],
    }), 'es');
    expect(m.find('dish-allergy').text()).toContain('Alergia: Frutos de cáscara, Altramuces');
    expect(m.find('dish-allergy-contains').text()).toBe('El plato lleva Altramuces');
  });
});

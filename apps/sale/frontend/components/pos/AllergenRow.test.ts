import { describe, expect, it } from 'vitest';

import { mountSale, settle } from '../../__tests__/mount-sale';
import AllergenRow from './AllergenRow.vue';

async function setup(codes: string[], locale: 'en' | 'es' = 'en') {
  const m = await mountSale(AllergenRow, { props: { codes, testid: 'allergens' }, locale });
  await settle();
  return m;
}

describe('AllergenRow', () => {
  it('formats the codes in the shared order and business language', async () => {
    const m = await setup(['milk', 'gluten'], 'es');
    expect(m.find('allergens').text()).toBe('Alérgenos: Gluten, Leche');
  });

  it('renders nothing without allergens', async () => {
    const m = await setup([]);
    expect(m.find('allergens').exists()).toBe(false);
  });
});

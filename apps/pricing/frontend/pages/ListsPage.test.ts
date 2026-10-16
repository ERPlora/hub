// Price Lists (WORKBOOK «Pantallas · Tarifas»): the old module's one screen, «Price lists» on top and
// «Discount rules» under it, each with its own table.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { mountPricing } from '../__tests__/mount-pricing';
import PriceListsTable from '../components/PriceListsTable.vue';
import RulesTable from '../components/RulesTable.vue';
import ListsPage from './ListsPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

describe('ListsPage', () => {
  it('stacks «Price lists» and «Discount rules» under the title «Price Lists»', async () => {
    const m = await mountPricing(ListsPage);
    expect(m.wrapper.findComponent(AppPage).props('title')).toBe('Price Lists');
    expect(m.wrapper.findAll('h2').map((h) => h.text())).toEqual(['Price lists', 'Discount rules']);
    expect(m.wrapper.findComponent(PriceListsTable).exists()).toBe(true);
    expect(m.wrapper.findComponent(RulesTable).exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const m = await mountPricing(ListsPage, { locale: 'es' });
    expect(m.wrapper.findComponent(AppPage).props('title')).toBe('Tarifas');
    expect(m.wrapper.findAll('h2').map((h) => h.text())).toEqual(['Listas de precios', 'Reglas de descuento']);
  });
});

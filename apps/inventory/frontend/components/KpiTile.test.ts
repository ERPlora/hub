// A figure of the inventory dashboard, as the old `ok-kpi` painted it (label in small capitals and its
// icon on top, the value big below, an optional note in the tone of what it means). A tile with `to`
// takes you there (WORKBOOK «Panel»: the first four figures lead to Products). Asked for as a shared
// component in UI-REQUESTS.md; this one stands in meanwhile.
import { describe, expect, it } from 'vitest';
import { RouterLink } from 'vue-router';

import { flush, mountInventory } from '../__tests__/mount-inventory';
import KpiTile from './KpiTile.vue';

describe('KpiTile', () => {
  it('paints its label, value, icon and note', async () => {
    const { wrapper } = await mountInventory(KpiTile, {
      props: { label: 'Inventory value', value: '1.234,56 €', icon: 'ion:wallet-outline', note: 'at cost', testid: 'kpi-value' },
    });
    expect(wrapper.get('[data-testid="kpi-value"]').attributes('data-value')).toBe('1.234,56 €');
    expect(wrapper.get('.kpi-tile__label').text()).toBe('Inventory value');
    expect(wrapper.get('.kpi-tile__value').text()).toBe('1.234,56 €');
    expect(wrapper.get('.kpi-tile__note').text()).toBe('at cost');
    expect(wrapper.find('.kpi-tile__icon').exists()).toBe(true);
    expect(wrapper.findComponent(RouterLink).exists()).toBe(false);
  });

  it('with `to` it is a link there; the warning tone colours its value', async () => {
    const m = await mountInventory(KpiTile, {
      props: { label: 'Low stock', value: '3', icon: 'ion:warning-outline', to: '/inventory/products', tone: 'warning', testid: 'kpi-low' },
    });
    const link = m.wrapper.findComponent(RouterLink);
    expect(link.props('to')).toBe('/inventory/products');
    expect(m.wrapper.get('[data-testid="kpi-low"]').attributes('data-tone')).toBe('warning');
    await link.trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/inventory/products');
  });

  it('without a note paints none', async () => {
    const { wrapper } = await mountInventory(KpiTile, { props: { label: 'In stock', value: '0', icon: 'ion:cube-outline' } });
    expect(wrapper.find('.kpi-tile__note').exists()).toBe(false);
  });
});

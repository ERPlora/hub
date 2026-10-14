// The four figures above the customer list (WORKBOOK «Pantallas · Clientes»): Customers, Active,
// VIP and Revenue (what the live cards spent), followed live from `customer.customer.stats`.
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountCustomer, subId } from '../__tests__/mount-customer';
import { formatMoney } from '../lib/money';
import CustomerStats from './CustomerStats.vue';
import source from './CustomerStats.vue?raw';

const STATS = { total: 12, active: 9, vip: 2, total_revenue: 123456 };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCustomer(CustomerStats, { locale });
  const call = await m.live();
  const kpi = (id: string) => m.wrapper.get(`[data-testid="customer-stats-${id}"]`);
  return { ...m, call, kpi };
}

describe('CustomerStats', () => {
  it('follows customer.customer.stats and shows «…» until the first result', async () => {
    const s = await setup();
    expect(s.params('customer.customer.stats')).toEqual([{}]);
    expect(s.wrapper.get('[data-testid="customer-stats"]').attributes('aria-busy')).toBe('true');
    expect(s.kpi('total').text()).toContain('…');
  });

  it('paints the four figures in the product order, revenue as money', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.customer.stats', STATS);
    const group = s.wrapper.get('[data-testid="customer-stats"]');
    expect([group.attributes('role'), group.attributes('aria-label'), group.attributes('aria-busy')]).toEqual([
      'group',
      'Figures',
      'false',
    ]);
    expect(['total', 'active', 'vip', 'revenue'].map((k) => s.kpi(k).find('.customer-kpi__label').text())).toEqual([
      'Customers',
      'Active',
      'VIP',
      'Revenue',
    ]);
    expect(['total', 'active', 'vip'].map((k) => s.kpi(k).find('.customer-kpi__value').text())).toEqual(['12', '9', '2']);
    expect(s.kpi('revenue').find('.customer-kpi__value').text()).toBe(formatMoney(123456, 'en'));
    expect(['total', 'active', 'vip', 'revenue'].map((k) => s.kpi(k).attributes('data-value'))).toEqual([
      '12',
      '9',
      '2',
      '123456',
    ]);
  });

  it('a new result replaces the figures (a write elsewhere re-ran the query)', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.customer.stats', STATS);
    await s.result(s.call, 'customer.customer.stats', { ...STATS, total: 13 }, 2);
    expect(s.kpi('total').attributes('data-value')).toBe('13');
  });

  it('says when the figures could not be loaded', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'customer.customer.stats'), 'boom'));
    await flush();
    expect(s.wrapper.get('[data-testid="customer-stats-error"]').text()).toBe('The figures could not be loaded');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.result(s.call, 'customer.customer.stats', STATS);
    expect(['total', 'active', 'vip', 'revenue'].map((k) => s.kpi(k).find('.customer-kpi__label').text())).toEqual([
      'Clientes',
      'Activos',
      'VIP',
      'Ingresos',
    ]);
    expect(s.kpi('revenue').find('.customer-kpi__value').text()).toBe(formatMoney(123456, 'es'));
  });

  it('lays the figures in a grid that fits two on a phone (cards of at least 9.5rem)', () => {
    expect(source).toMatch(/grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(9\.5rem,\s*1fr\)\)/);
  });

  it('has no OutfitKit tag and formats nothing by hand', () => {
    expect(source).not.toMatch(/<ok[-]/);
    expect(source).not.toMatch(/Intl\.|toLocale|toFixed/);
  });
});

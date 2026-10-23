// The six figures of the period on Sales (SALE-F28): «Tickets», «Revenue» (refunds already taken off),
// «Avg. ticket», the tax, «Discounts» and «Voided», from `sale.sale.stats` over the same business days as
// the rows, live. The tax figure is named by the tax its sales were declared with (`tax_kind` of the stats:
// «VAT», «IGIC», «IPSI»), never by the territory kept today; sales of more than one tax make it a plain
// «Taxes»; a period without sales (or figures not read yet) names it by the business territory's, as Taxes
// publishes it (`useTaxName`, live). Until they arrive, and when they cannot be read, each figure says «—» (a
// figure that could not be read is not a zero), and a failure adds «Error loading metrics».
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountSale, taxSettings } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import type { StatsOut } from '../../operations';
import SalesKpis from './SalesKpis.vue';
import source from './SalesKpis.vue?raw';

const STATS: StatsOut = {
  count: 1234,
  total_revenue: 1250050,
  avg_ticket: 1013,
  net_total: 1100000,
  tax_total: 150050,
  discount_total: 2500,
  refunded_total: 500,
  voided_count: 3,
  tax_kind: 'vat',
};
/** The figures of a period without a sale: the server names its tax by the territory's. */
const NO_SALES: StatsOut = {
  count: 0,
  total_revenue: 0,
  avg_ticket: 0,
  net_total: 0,
  tax_total: 0,
  discount_total: 0,
  refunded_total: 0,
  voided_count: 0,
  tax_kind: 'vat',
};

const KEYS = ['tickets', 'revenue', 'avg-ticket', 'tax', 'discounts', 'voided'];

async function setup(bounds: Record<string, string> = { date_from: '2026-10-14', date_to: '2026-10-14' }, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(SalesKpis, { props: { bounds }, locale });
  const call = await m.live();
  const cards = () => KEYS.map((key) => [plain(m.find(`sales-kpi-${key}-label`).text()), plain(m.find(`sales-kpi-${key}`).text())]);
  return { ...m, call, cards };
}

describe('SalesKpis', () => {
  it('reads the figures of the same business days as the rows', async () => {
    const s = await setup();
    expect(s.params('sale.sale.stats')).toEqual([{ date_from: '2026-10-14', date_to: '2026-10-14' }]);
    await s.wrapper.setProps({ bounds: {} });
    await s.reopen();
    expect(s.params('sale.sale.stats')).toEqual([{}]);
  });

  it('shows «—» until they arrive, then the six figures in the reader’s language', async () => {
    const s = await setup();
    expect(s.cards().map(([, value]) => value)).toEqual(['—', '—', '—', '—', '—', '—']);
    await s.result('sale.sale.stats', STATS);
    expect(s.cards()).toEqual([
      ['Tickets', '1,234'],
      ['Revenue', '€12,500.50'],
      ['Avg. ticket', '€10.13'],
      ['VAT', '€1,500.50'],
      ['Discounts', '€25.00'],
      ['Voided', '3'],
    ]);
    expect(s.find('sales-kpis-error').exists()).toBe(false);
  });

  it('a failure shows «—» everywhere and «Error loading metrics»', async () => {
    const s = await setup();
    await s.result('sale.sale.stats', STATS);
    s.call.push(errorFrame(s.subId('sale.sale.stats'), 'sale.boom'));
    await flush();
    expect(s.cards().map(([, value]) => value)).toEqual(['—', '—', '—', '—', '—', '—']);
    expect(s.find('sales-kpis-error').text()).toContain('Error loading metrics');
  });

  it('speaks Spanish', async () => {
    const s = await setup(undefined, 'es');
    await s.result('sale.sale.stats', STATS);
    expect(s.cards()).toEqual([
      ['Tickets', '1234'],
      ['Ingresos', '12.500,50 €'],
      ['Ticket medio', '10,13 €'],
      ['IVA', '1.500,50 €'],
      ['Descuentos', '25,00 €'],
      ['Anuladas', '3'],
    ]);
    s.call.push(errorFrame(s.subId('sale.sale.stats'), 'sale.boom'));
    await flush();
    expect(s.find('sales-kpis-error').text()).toContain('Error cargando métricas');
  });

  it.each([
    ['vat', 'en', 'VAT'],
    ['igic', 'en', 'IGIC'],
    ['ipsi', 'en', 'IPSI'],
    ['vat', 'es', 'IVA'],
    ['igic', 'es', 'IGIC'],
    ['ipsi', 'es', 'IPSI'],
  ] as const)('sales that all declared %s in %s name the tax «%s», whatever the territory is now', async (tax, locale, label) => {
    const s = await setup(undefined, locale);
    // The territory kept today is another one: what the sales declared wins.
    await s.result('tax.settings.get', taxSettings(tax === 'igic' ? 'vat' : 'igic'));
    await s.result('sale.sale.stats', { ...STATS, tax_kind: tax });
    expect(s.cards()[3]).toEqual([label, locale === 'es' ? '1.500,50 €' : '€1,500.50']);
  });

  it.each([
    ['en', 'Taxes', '€1,500.50'],
    ['es', 'Impuestos', '1.500,50 €'],
  ] as const)('sales of more than one tax name it a plain «Taxes» (%s)', async (locale, label, value) => {
    const s = await setup(undefined, locale);
    await s.result('tax.settings.get', taxSettings('igic'));
    await s.result('sale.sale.stats', { ...STATS, tax_kind: null });
    expect(s.cards()[3]).toEqual([label, value]);
  });

  it('a change of territory does not rename the tax of sales already declared', async () => {
    const s = await setup();
    await s.result('tax.settings.get', taxSettings('igic'));
    await s.result('sale.sale.stats', { ...STATS, tax_kind: 'igic' });
    await s.result('tax.settings.get', taxSettings('vat'), {}, 2);
    expect(s.cards()[3]).toEqual(['IGIC', '€1,500.50']);
  });

  it('a period without sales names the tax by the business territory’s, and follows a change of it', async () => {
    const s = await setup();
    await s.result('sale.sale.stats', NO_SALES);
    await s.result('tax.settings.get', taxSettings('igic'));
    expect(s.cards()[3]).toEqual(['IGIC', '€0.00']);
    await s.result('tax.settings.get', taxSettings('ipsi'), {}, 2);
    expect(s.cards()[3]).toEqual(['IPSI', '€0.00']);
  });

  it('until the figures arrive, or when they cannot be read, the tax is named by the territory’s', async () => {
    const s = await setup(undefined, 'es');
    await s.result('tax.settings.get', taxSettings('igic'));
    expect(s.cards()[3]).toEqual(['IGIC', '—']);
    await s.result('sale.sale.stats', { ...STATS, tax_kind: null });
    expect(s.cards()[3][0]).toBe('Impuestos');
    s.call.push(errorFrame(s.subId('sale.sale.stats'), 'sale.boom'));
    await flush();
    expect(s.cards()[3]).toEqual(['IGIC', '—']);
  });

  it('below 768 px the cards are one row that scrolls sideways', () => {
    expect(source.replace(/\s+/g, ' ')).toMatch(/@media \(max-width: 767\.98px\) \{ \.sale-kpis \{[^}]*flex-wrap: nowrap;[^}]*overflow-x: auto;/);
  });
});

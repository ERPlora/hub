// flow: SALE-F28 (SALE-G01) — with the period «7 days», what was sold each of those business days, today last
// (`sale.sale.last_7_days`, live): the old Home's «Last 7 days» panel, inside Sales. A day without sales says
// 0,00 €; a failure says so.
import { describe, expect, it } from 'vitest';

import { business, errorFrame, JAPANESE, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import SalesWeek from './SalesWeek.vue';

const OP = 'sale.sale.last_7_days';
const DAYS = ['2026-10-14', '2026-10-15', '2026-10-16', '2026-10-17', '2026-10-18', '2026-10-19', '2026-10-20'];

async function setup() {
  const m = await mountSale(SalesWeek, { locale: 'es' });
  await m.live();
  return m;
}

describe('SalesWeek', () => {
  it('lists the seven business days, oldest first, each with what was sold', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    await s.result(OP, { rows: DAYS.map((day, at) => ({ day, total: at === 6 ? 12550 : at * 100 })) });
    expect(s.find('sale-week').attributes('aria-label')).toBe('Últimos 7 días');
    const days = s.wrapper.findAll('[data-testid="sale-week-day"]').map((day) => plain(day.text()));
    expect(days).toHaveLength(7);
    expect(days[0]).toContain('0,00 €');
    expect(days[0]).toMatch(/mi/i);
    expect(days[6]).toContain('125,50 €');
    expect(days[6]).toContain('20');
  });

  // hub#936: until the business says its money, a day's total is «—», never 125,50 for 12,550 yen.
  it('a day’s total waits for the business’s money', async () => {
    const m = await mountSale(SalesWeek, { locale: 'es', business: null });
    await m.live();
    await m.result(OP, { rows: DAYS.map((day) => ({ day, total: 12550 })) });
    const last = () => plain(m.wrapper.findAll('[data-testid="sale-week-day"]')[6]?.text() ?? '');
    expect(last()).toContain('—');
    expect(last()).not.toContain('125,50');
    await m.result('base.business.get', business(JAPANESE));
    expect(last()).toContain('12.550 ¥');
  });

  it('a failure says so', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await s.reopen();
    expect(s.find('sale-week-error').text()).toContain('No se han podido leer los últimos 7 días.');
  });
});

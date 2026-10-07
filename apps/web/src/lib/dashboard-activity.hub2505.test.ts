// hub#2505 — Home's «Activity» tab painted every sale a hundred times bigger: a 12,50 € ticket read
// «1.250,00 €». `sales` stores and serves `total` in MINOR units (cents, `001_init.sql`), and the
// feed handed it to `formatAmount`, the formatter for amounts that already arrive in euros. Every
// other screen that paints a sale (the sales history, the Home panels) uses `formatMoney`.
//
// The old test fed `total: '12.5'` — euros, a shape `sales.list` never serves — which is why it
// never saw the bug. These rows are what the real query answers.
//
// The same tab also named every sale that was not completed «Pending»: a voided or refunded sale
// read as money still to come in.
import { afterEach, describe, expect, it } from 'vitest';

import { ACTIVITY_STATUS_KEY, formatActivityAmount, loadRecentSales } from './dashboard-activity';
import { hubSettings } from './hub-settings';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

// CLDR puts a NO-BREAK SPACE (U+00A0) between the figure and the € in Spanish.
const NBSP = '\u00a0';

function pageOf(rows: Record<string, unknown>[]) {
  return {
    queryPage: async <T = unknown>() => ({ rows: rows as T[], total: rows.length, limit: 100, offset: 0 }),
  };
}

afterEach(() => {
  hubSettings.value = null;
});

describe('the activity feed paints the sale total as money in cents (hub#2505)', () => {
  it('a 12,50 € sale (total 1250 cents) reads «12,50 €», not «1.250,00 €»', async () => {
    const [row] = await loadRecentSales(pageOf([{ id: 's1', total: 1250, status: 'completed' }]), new Set(['sales']));

    expect(formatActivityAmount(row, { locale: 'es' })).toBe(`12,50${NBSP}€`);
    expect(formatActivityAmount(row, { locale: 'en' })).toBe('€12.50');
  });

  it('Postgres BIGINT totals arrive as text and are still cents', async () => {
    const [row] = await loadRecentSales(
      pageOf([{ id: 's1', total: '123456', status: 'completed' }]),
      new Set(['sales']),
    );

    expect(formatActivityAmount(row, { locale: 'es' })).toBe(`1.234,56${NBSP}€`);
  });

  it('scales by the decimals of the hub currency, not a blind ÷100 (a yen hub)', async () => {
    hubSettings.value = { currency: 'JPY', currency_decimals: 0 } as typeof hubSettings.value;
    const [row] = await loadRecentSales(pageOf([{ id: 's1', total: 1500, status: 'completed' }]), new Set(['sales']));

    expect(formatActivityAmount(row, { locale: 'en' })).toBe('¥1,500');
  });
});

describe('the activity feed names each sale state for what it is (hub#2505)', () => {
  it('voided, refunded, pending and draft sales are not lumped together as «Pending»', async () => {
    const rows = await loadRecentSales(
      pageOf([
        { id: 'a', total: 100, status: 'completed' },
        { id: 'b', total: 100, status: 'voided' },
        { id: 'c', total: 100, status: 'refunded' },
        { id: 'd', total: 100, status: 'pending' },
        { id: 'e', total: 100, status: 'draft' },
        { id: 'f', total: 100, status: 'something_new' },
        { id: 'g', total: 100, status: 'toString' },
      ]),
      new Set(['sales']),
    );

    expect(rows.map((r) => [r.status, r.tone])).toEqual([
      ['completed', 'success'],
      ['voided', 'danger'],
      ['refunded', 'warning'],
      ['pending', 'medium'],
      ['draft', 'medium'],
      ['other', 'medium'],
      ['other', 'medium'],
    ]);
  });

  it('every state has its words in English and Spanish, and they are all different', () => {
    const lookup = (catalog: Record<string, unknown>, key: string): unknown =>
      key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog);

    for (const catalog of [en, es] as Record<string, unknown>[]) {
      const words = Object.values(ACTIVITY_STATUS_KEY).map((key) => lookup(catalog, key));
      for (const word of words) expect(typeof word, `missing translation in ${String(words)}`).toBe('string');
      expect(new Set(words).size, 'two states share one word').toBe(words.length);
    }
    expect(lookup(es as Record<string, unknown>, ACTIVITY_STATUS_KEY.voided)).toBe('Anulada');
    expect(lookup(es as Record<string, unknown>, ACTIVITY_STATUS_KEY.refunded)).toBe('Devuelta');
  });
});

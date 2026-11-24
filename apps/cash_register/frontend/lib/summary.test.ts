// The figures of a session, as the detail shows them and the X/Z report prints them (CASH_REGISTER-F11,
// F16): status, drawer, who opened and closed it and when, the lines, the float, the sales and their
// split by payment method (only when the server shows it), refunds, cash in and out, comps, expected,
// counted, difference with its sign, and the notes. An open session shows «—» counted and difference. What another
// app records (Tips, CASH_REGISTER-F18) goes apart, just before the expected.
import { describe, expect, it } from 'vitest';

import type { SessionOut } from '../operations';
import { plain } from './money';
import { appLineItems, summaryItems } from './summary';

const t = (key: string, named?: Record<string, unknown>) => (named ? `${key.split('.').at(-1)}(${Object.values(named).join('|')})` : key.split('.').at(-1)!);
const date = (iso: string | null) => (iso ? iso.slice(11, 16) : '');

const session = (over: Partial<SessionOut> = {}): SessionOut => ({
  id: 's1',
  number: 'S-261014-0001',
  business_day: '2026-10-14',
  status: 'closed',
  register_id: 'r1',
  register_name: 'Bar',
  opened_at: '2026-10-14T08:00:00Z',
  opened_by: 'ana',
  opening_balance: 10000,
  closed_at: '2026-10-14T20:00:00Z',
  closed_by: 'luis',
  closing_balance: 9950,
  expected_balance: 10000,
  difference: -50,
  auto_closed: false,
  expected_hidden: false,
  auto_close_due: false,
  opening_notes: 'Morning',
  closing_notes: '',
  summary: {
    movement_count: 3,
    opening_balance: 10000,
    total_sales: 450,
    cash_sales: 300,
    card_sales: 150,
    other_sales: 0,
    total_refunds: 0,
    total_cash_in: 0,
    total_cash_out: 300,
    total_gifts: 40,
    app_lines: [],
    expected_cash: 10000,
    counted: 9950,
    difference: -50,
  },
  ...over,
});

const EUR = { currency: 'EUR', decimals: 2 };
const TIPS = [
  { app: 'tip', label: 'Tips in cash', amount: 500 },
  { app: 'tip', label: 'Tips by card', amount: 700 },
  { app: 'tip', label: 'Tips paid out', amount: -200 },
];

const read = (s: SessionOut) => Object.fromEntries(summaryItems(s, t, 'en', date, { currency: 'EUR', decimals: 2 }).map((item) => [item.key, plain(item.value)]));

describe('summaryItems', () => {
  it('a closed session: who and when, every figure, the difference with its sign and the notes written', () => {
    const items = summaryItems(session(), t, 'en', date, { currency: 'EUR', decimals: 2 });
    expect(items.map((item) => item.key)).toEqual([
      'status',
      'register',
      'opened',
      'closed',
      'movements',
      'opening',
      'sales',
      'cashSales',
      'cardSales',
      'refunds',
      'cashIn',
      'cashOut',
      'gifts',
      'expected',
      'counted',
      'difference',
      'openingNotes',
    ]);
    expect(read(session())).toMatchObject({
      status: 'closed',
      register: 'Bar',
      opened: 'by(08:00|ana)',
      closed: 'by(20:00|luis)',
      movements: '3',
      cashSales: '€3.00',
      expected: '€100.00',
      counted: '€99.50',
      difference: '-€0.50',
      gifts: '€0.40',
      openingNotes: 'Morning',
    });
  });

  it('an open session: no close, «—» counted and difference; other methods only when there were', () => {
    const open = session({ status: 'open', closed_at: null, closed_by: '', closing_balance: null, difference: null });
    open.summary = { ...open.summary, other_sales: 120, counted: null, difference: null };
    expect(read(open)).toMatchObject({ closed: '—', counted: '—', difference: '—', otherSales: '€1.20' });
  });

  it('a blind count shows no figure that adds up to the expected', () => {
    const blind = session({ status: 'open', closed_at: null });
    blind.summary = {
      ...blind.summary,
      total_sales: null,
      cash_sales: null,
      card_sales: null,
      other_sales: null,
      total_refunds: null,
      total_cash_in: null,
      total_cash_out: null,
      total_gifts: null,
      expected_cash: null,
    };
    const keys = summaryItems(blind, t, 'en', date, { currency: 'EUR', decimals: 2 }).map((item) => item.key);
    expect(keys).not.toContain('cashSales');
    expect(read(blind)).toMatchObject({ opening: '€100.00', sales: '—', refunds: '—', cashIn: '—', cashOut: '—', gifts: '—', expected: '—' });
  });

  it('a session closed by itself says so', () => {
    expect(read(session({ auto_closed: true, closed_by: '' })).closed).toBe('closedAuto(20:00)');
  });

  it("another app's lines go apart just before the expected, as the server names them and with their sign", () => {
    const tips = session();
    tips.summary = { ...tips.summary, app_lines: TIPS };
    const items = summaryItems(tips, t, 'en', date, EUR);
    const keys = items.map((item) => item.key);
    expect(keys.slice(keys.indexOf('gifts') + 1, keys.indexOf('expected'))).toEqual(['tip-0', 'tip-1', 'tip-2']);
    expect(items.filter((item) => item.key.startsWith('tip-')).map((item) => [item.label, plain(item.value)])).toEqual([
      ['Tips in cash', '€5.00'],
      ['Tips by card', '€7.00'],
      ['Tips paid out', '-€2.00'],
    ]);
  });

  it('a session without them, or a blind count that hides them, shows no line of an app', () => {
    const blind = session();
    blind.summary = { ...blind.summary, app_lines: null };
    for (const shown of [session(), blind]) {
      expect(summaryItems(shown, t, 'en', date, EUR).map((item) => item.key)).not.toContainEqual(expect.stringMatching(/^tip-/));
    }
  });
});

describe('appLineItems', () => {
  it("writes each line in the reader's money, keyed by its app and its place", () => {
    const lines = [...TIPS.slice(0, 1), { app: 'demo', label: 'Demo in cash', amount: 1250 }];
    expect(appLineItems(lines, 'es', EUR).map((item) => [item.key, item.label, plain(item.value)])).toEqual([
      ['tip-0', 'Tips in cash', '5,00 €'],
      ['demo-1', 'Demo in cash', '12,50 €'],
    ]);
    expect(appLineItems(null, 'es', EUR)).toEqual([]);
  });
});

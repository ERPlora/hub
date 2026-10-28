// How the staff screens paint and read money, rates, calendar dates and wall-clock times (pages never
// format by hand). Money is whole minor units of the business's currency (its country's, with the decimals
// the server counts it in: `useBusinessMoney`); until the business answers an amount is a figure without a
// symbol, never in euros by default. A calendar date (`YYYY-MM-DD`) is a day, not an instant, so it is
// painted in UTC and never moves a day; a time is the wall clock of the business (`HH:MM:SS` on the wire,
// `HH:MM` in a time field).
import { describe, expect, it } from 'vitest';

import {
  centsFromText,
  currencySymbol,
  formatDate,
  formatMoney,
  formatPercent,
  formatTime,
  hoursSummary,
  type Money,
  moneyText,
  timeValue,
} from './format';

const EURO: Money = { currency: 'EUR', decimals: 2 };
const ZLOTY: Money = { currency: 'PLN', decimals: 2 };
const YEN: Money = { currency: 'JPY', decimals: 0 };
/** Intl's no-break spaces as plain ones, to compare what a person reads. */
const plain = (text: string) => text.replace(/\s/g, ' ');

describe('formatMoney', () => {
  it('paints whole minor units in the business\'s currency, in the reader’s language', () => {
    // Intl keeps the amount and the sign together with a no-break space.
    expect(formatMoney(1250, 'es', EURO)).toBe('12,50\u00a0€');
    expect(formatMoney(1250, 'en', EURO)).toBe('€12.50');
    expect(formatMoney(0, 'en', EURO)).toBe('€0.00');
  });

  it('a business in Poland reads złoty, never euros', () => {
    expect(plain(formatMoney(1250, 'es', ZLOTY))).toBe('12,50 zł');
    expect(plain(formatMoney(1250, 'en', ZLOTY))).toBe('zł 12.50');
  });

  it('a business in Japan reads yen with the decimals the server counts (none): 1500 is ¥1,500', () => {
    expect(formatMoney(1500, 'en', YEN)).toBe('¥1,500');
    expect(plain(formatMoney(1500, 'es', YEN))).toBe('1500 ¥');
  });

  it('until the business answers, a figure without a symbol, never euros', () => {
    expect(formatMoney(1250, 'es')).toBe('12,50');
    expect(formatMoney(1250, 'en')).toBe('12.50');
  });
});

describe('currencySymbol (the end of the hourly-rate field)', () => {
  it('the symbol a till of that country prints; nothing until the business answers', () => {
    expect(currencySymbol('es', EURO)).toBe('€');
    expect(currencySymbol('es', ZLOTY)).toBe('zł');
    expect(currencySymbol('en', YEN)).toBe('¥');
    expect(currencySymbol('es')).toBe('');
  });
});

describe('moneyText and centsFromText (the hourly-rate field)', () => {
  it('shows cents as the figure a person types, in their decimal mark', () => {
    expect(moneyText(1250, 'es')).toBe('12,50');
    expect(moneyText(1250, 'en')).toBe('12.50');
    expect(moneyText(0, 'en')).toBe('0.00');
  });

  it('reads what a person types back into whole cents, with a comma or a point', () => {
    expect(centsFromText('12,50')).toBe(1250);
    expect(centsFromText('12.5')).toBe(1250);
    expect(centsFromText(' 9 ')).toBe(900);
    expect(centsFromText('0.015')).toBe(2);
  });

  it('an empty field is no rate (0); what is not a figure is null (the server would refuse it)', () => {
    expect(centsFromText('')).toBe(0);
    expect(centsFromText('  ')).toBe(0);
    expect(centsFromText('doce')).toBeNull();
    expect(centsFromText('1.250,50')).toBeNull();
  });

  it('keeps a negative figure negative, for the server to say why it refuses it under the field', () => {
    expect(centsFromText('-3')).toBe(-300);
  });

  // gh:staff#64: the rate was read and written on the euro's scale whatever the business's currency.
  it('reads and writes with the decimals of the business\'s currency: in yen «1500» is 1500, not 150000', () => {
    expect(moneyText(1500, 'es', YEN)).toBe('1500');
    expect(moneyText(1500, 'en', YEN)).toBe('1500');
    expect(centsFromText('1500', YEN)).toBe(1500);
    expect(centsFromText('1500', ZLOTY)).toBe(150000);
    expect(moneyText(1250, 'es', ZLOTY)).toBe('12,50');
    expect(centsFromText('12,50', ZLOTY)).toBe(1250);
  });

  it('a figure with more decimals than the currency has is rounded to it (in yen, to the unit)', () => {
    expect(centsFromText('12,5', YEN)).toBe(13);
    expect(centsFromText('0.015', EURO)).toBe(2);
  });

  it('until the business answers, two decimals, as typed', () => {
    expect(moneyText(1250, 'es')).toBe('12,50');
    expect(centsFromText('12,50')).toBe(1250);
  });
});

describe('formatPercent', () => {
  it('paints the commission without trailing zeros, in the reader’s decimal mark', () => {
    expect(formatPercent('12.50', 'es')).toBe('12,5 %');
    expect(formatPercent('10.00', 'en')).toBe('10 %');
    expect(formatPercent('0.00', 'en')).toBe('0 %');
  });
});

describe('formatDate', () => {
  it('paints a calendar day in the reader’s order, never a day off west of Greenwich', () => {
    expect(formatDate('2026-10-05', 'es')).toBe('05/10/2026');
    expect(formatDate('2026-10-05', 'en')).toBe('10/05/2026');
  });

  it('nothing to show is a dash; what is not a date comes back as it was', () => {
    expect(formatDate(null, 'en')).toBe('—');
    expect(formatDate('', 'en')).toBe('—');
    expect(formatDate('soon', 'en')).toBe('soon');
  });
});

describe('formatTime and timeValue', () => {
  it('paints a wall-clock time as HH:MM', () => {
    expect(formatTime('09:00:00')).toBe('09:00');
    expect(formatTime('13:30')).toBe('13:30');
    expect(formatTime(null)).toBe('');
  });

  it('timeValue: the HH:MM a time field holds, empty for none', () => {
    expect(timeValue('18:00:00')).toBe('18:00');
    expect(timeValue(null)).toBe('');
  });
});

describe('hoursSummary (the «Hours» column of Schedules)', () => {
  const short = (day: number) => ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day];

  it('says the week at a glance, by weekday, with the break in brackets', () => {
    const days = [
      { weekday: 2, start_time: '10:00:00', end_time: '16:00:00', break_start: null, break_end: null },
      { weekday: 0, start_time: '09:00:00', end_time: '18:00:00', break_start: '13:00:00', break_end: '14:00:00' },
    ];
    expect(hoursSummary(days, short)).toBe('Mon 09:00–18:00 (13:00–14:00) · Wed 10:00–16:00');
  });

  it('a week without working days is a dash', () => {
    expect(hoursSummary([], short)).toBe('—');
  });
});

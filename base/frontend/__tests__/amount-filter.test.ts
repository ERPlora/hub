// The table of texts every list with an amount filter runs (hub#1196, `amount-filter.ts`): each row is how the platform's
// money field reads the text (`parseMoney`), what it says for one it cannot read is the field's own words, and a list
// that reads with the platform's pair (`filterCents`, `amountFilterErrors`) passes it.
import { type Money, parseMoney } from '@erplora/ui/components';
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import { amountFilterErrors, filterCents, formatMoney } from '../lib/money';
import { AMOUNT_FILTER_TEXTS, type AmountReading, EUR, itReadsAmountFiltersAsTheHub, JPY, KWD, moneyFieldSays } from './amount-filter';

/** `parseMoney`'s reading of `typed` in `money`, as the table writes it (no text of the table is empty). */
function platform(typed: string, money: Money): AmountReading {
  const read = parseMoney(typed, { money });
  if (read.ok) return read.cents as number;
  return read.reason === 'ambiguous' ? { grouped: read.grouped, decimal: read.decimal } : read.reason;
}

describe('the table of amount filter texts (hub#1196)', () => {
  it('reads each text as the money field does, in euros, in yen and in dinars', () => {
    expect(
      AMOUNT_FILTER_TEXTS.map(({ typed }) => ({ typed, EUR: platform(typed, EUR), JPY: platform(typed, JPY), KWD: platform(typed, KWD) })),
    ).toEqual(AMOUNT_FILTER_TEXTS);
  });

  it('has the texts that split the lists: thousands, both conventions, spaces, a symbol, «1.000», a minus and letters', () => {
    expect(AMOUNT_FILTER_TEXTS.map(({ typed }) => typed)).toEqual(
      expect.arrayContaining(['12', '12,5', '1.000', '1.000,50', '1,000.50', '2 500', '12,50 €', '-5']),
    );
  });

  it('says for a text it cannot read what the money field says, in its words; nothing for an amount', () => {
    expect([
      moneyFieldSays('1.000', { grouped: 100000, decimal: 100 }, EUR),
      moneyFieldSays('doce', 'not_amount', EUR),
      moneyFieldSays('doce', 'not_amount', JPY),
      moneyFieldSays('doce', 'not_amount', KWD),
      moneyFieldSays('-5', 'negative', JPY),
      moneyFieldSays('12', 1200, EUR),
    ]).toEqual([
      `This amount can be read in two ways: «1.000» could be ${formatMoney(100000, 'en', EUR)} or ${formatMoney(100, 'en', EUR)}. Write the decimals so there is no doubt.`,
      'This is not an amount. Type a figure, for example 12.50.',
      'This is not an amount. Type a figure, for example 12.',
      'This is not an amount. Type a figure, for example 12.500.',
      'This amount cannot be negative.',
      undefined,
    ]);
  });
});

describe('a list that reads its amount filter with the platform', () => {
  const i18n = createShellI18n({ locale: 'en', messages: { en, es } });
  const t = (key: string, named?: Record<string, unknown>) => (named ? i18n.global.t(key, named) : i18n.global.t(key));
  itReadsAmountFiltersAsTheHub({
    ends: ['spent_from', 'spent_to'],
    params: ['spent_min', 'spent_max'],
    async open(money) {
      let values: Record<string, string> = {};
      return {
        filter: async (now) => {
          values = now;
        },
        query: () => ({ spent_min: filterCents(values.spent_from, money), spent_max: filterCents(values.spent_to, money) }),
        says: () => amountFilterErrors(values, ['spent_from', 'spent_to'], { money, t, locale: 'en' }),
      };
    },
  });
});

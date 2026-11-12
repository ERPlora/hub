// Test helper of every list whose table filters an amount «from / to» (hub#1196). Such a list reads what a person types
// there the way every money field of the Hub reads it — the platform's `parseMoney` (`@erplora/ui/components`), through
// `filterCents` and `amountFilterErrors` of `base/frontend/lib/money.ts` — and says under the end it cannot read what
// the money field (`MoneyInput`) says for it. `itReadsAmountFiltersAsTheHub` types each text of `AMOUNT_FILTER_TEXTS`
// in both ends of one of the list's amount ranges, in a business in euros and in one in yen: the list asks for exactly
// those minor units, or for nothing and says why («1.000» in euros: its two readings). Each list's test calls it in one
// line, with its own mount (`amount-filters.test.ts` checks that every list with an amount filter does). A text that is
// no amount says it with an example in the business's money: «12.50» in euros, «12» in yen, «12.500» in dinars (ui#140).
import { formatMoney, type Money } from '@erplora/ui/components';
import { expect, it } from 'vitest';

import moneyField from '../../../packages/ui/src/components/MoneyInput/locales/en.json';

export const EUR: Money = { currency: 'EUR', decimals: 2 };
export const JPY: Money = { currency: 'JPY', decimals: 0 };
export const KWD: Money = { currency: 'KWD', decimals: 3 };

/** The example the money field gives, in English, for a text that is no amount of each money (ui#140). */
const EXAMPLE: Record<string, string> = { EUR: '12.50', JPY: '12', KWD: '12.500' };

/** How the Hub reads a text in one money: its minor units, or why it is no amount (`grouped`/`decimal`: the two
 *  readings of an ambiguous one). */
export type AmountReading = number | 'not_amount' | 'negative' | { grouped: number; decimal: number };

export interface AmountFilterText {
  typed: string;
  EUR: AmountReading;
  JPY: AmountReading;
  KWD: AmountReading;
}

/** What a person types in an amount filter, and how the Hub reads it in euros, in yen and in Kuwaiti dinars (three
 *  decimals): grouped thousands in either convention, a space, the currency's symbol (and another's), «1.000» (1.000 €
 *  or 1 €; 1.000 ¥; 1 KD), decimals the yen has not, a minus and letters. */
export const AMOUNT_FILTER_TEXTS: readonly AmountFilterText[] = [
  { typed: '12', EUR: 1200, JPY: 12, KWD: 12000 },
  { typed: '12,5', EUR: 1250, JPY: 'not_amount', KWD: 12500 },
  { typed: '1.000', EUR: { grouped: 100000, decimal: 100 }, JPY: 1000, KWD: 1000 },
  { typed: '1.000,50', EUR: 100050, JPY: 'not_amount', KWD: 1000500 },
  { typed: '1,000.50', EUR: 100050, JPY: 'not_amount', KWD: 1000500 },
  { typed: '2 500', EUR: 250000, JPY: 2500, KWD: 2500000 },
  { typed: '12,50 €', EUR: 1250, JPY: 'not_amount', KWD: 'not_amount' },
  { typed: '¥1.500', EUR: 'not_amount', JPY: 1500, KWD: 'not_amount' },
  { typed: '-5', EUR: 'negative', JPY: 'negative', KWD: 'negative' },
  { typed: 'doce', EUR: 'not_amount', JPY: 'not_amount', KWD: 'not_amount' },
];

/** What the money field says under itself for `typed`, read as `reading` in `money`, in English; nothing for an
 *  amount. */
export function moneyFieldSays(typed: string, reading: AmountReading, money: Money): string | undefined {
  if (typeof reading === 'number') return undefined;
  if (reading === 'not_amount') return moneyField.moneyInput.notAmount.replace('{amount}', EXAMPLE[money.currency]);
  if (reading === 'negative') return moneyField.moneyInput.negative;
  return moneyField.moneyInput.ambiguous
    .replace('{typed}', typed.trim())
    .replace('{grouped}', formatMoney(reading.grouped, 'en', money))
    .replace('{decimal}', formatMoney(reading.decimal, 'en', money));
}

/** A list mounted in English, its first page answered, ready to filter. */
export interface AmountFilterProbe {
  /** Applies the table's funnel: the filters by name, as typed. */
  filter: (values: Record<string, string>) => Promise<void>;
  /** The list's query now (what its table asks the server for). */
  query: () => Record<string, unknown> | undefined;
  /** What the table says under each filter (its `filterErrors`). */
  says: () => Record<string, string>;
}

export interface AmountFilterList {
  /** The list mounted in a business in `money`. */
  open: (money: Money) => Promise<AmountFilterProbe>;
  /** One amount range of its table, its two ends by the names the funnel gives them… */
  ends: readonly [string, string];
  /** …and by the names the list's query takes them, in minor units. */
  params: readonly [string, string];
}

/** One test per text of `AMOUNT_FILTER_TEXTS` and money: the list asks for and says what the platform reads. */
export function itReadsAmountFiltersAsTheHub(list: AmountFilterList): void {
  const cases = AMOUNT_FILTER_TEXTS.flatMap((row) =>
    ([[EUR, row.EUR], [JPY, row.JPY], [KWD, row.KWD]] as const).map(([money, reading]) => [`«${row.typed}» in ${money.currency}`, { typed: row.typed, money, reading }] as const),
  );
  it.each(cases)('%s is read as in the rest of the Hub (hub#1196)', async (_, { typed, money, reading }) => {
    const probe = await list.open(money);
    await probe.filter({ [list.ends[0]]: typed, [list.ends[1]]: typed });
    const query = probe.query() ?? {};
    const says = probe.says();
    const cents = typeof reading === 'number' ? reading : undefined;
    const message = moneyFieldSays(typed, reading, money);
    expect({ asks: list.params.map((name) => query[name]), says: list.ends.map((name) => says[name]) }).toEqual({
      asks: [cents, cents],
      says: [message, message],
    });
  });
}

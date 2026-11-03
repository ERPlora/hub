// How the combo screens paint money (pages never format by hand), always in the page language's own
// format (Intl). Money is whole minor units of the business's currency (`useBusinessMoney`, the platform's: its
// country's currency with the decimals the server counts it in, never the browser's Intl, which gives none to the
// forint), written with the platform's `formatMoney`: its thousands grouped from four digits on, as every screen
// writes them. Until the business answers an amount is a figure without a symbol, never the euro by default. A
// supplement shows its sign, as the till does.
import { formatMoney as writeMoney } from '@erplora/ui/components';

import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

/** Minor units in `money`, in `locale`, its thousands grouped («1.234,50 €», «€22.50», «¥1,500»; «22,50» while it is unknown). */
export const formatMoney: (cents: number, locale: string, money?: Money) => string = writeMoney;

/** The decimals of an amount while the currency is unknown. */
const UNKNOWN_DECIMALS = 2;

/** The decimals of an amount in `money`; two while it is unknown. */
export const moneyDecimals = (money?: Money): number => money?.decimals ?? UNKNOWN_DECIMALS;

const decimalMarks = new Map<string, string>();

/** The decimal mark of `locale` («,» in Spanish, «.» in English). */
export function decimalMark(locale: string): string {
  let found = decimalMarks.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';
    decimalMarks.set(locale, found);
  }
  return found;
}

/** A supplement in `money` with its sign («+2,00 zł», «-zł 0.50»; «+2,00» while it is unknown); `''` for none. */
export function formatDelta(cents: number, locale: string, money?: Money): string {
  if (!cents) return '';
  const written = formatMoney(cents, locale, money);
  return cents > 0 ? `+${written}` : written;
}

// How the combo screens paint money (pages never format by hand), always in the page language's own
// format (Intl). Money is whole minor units of the business's currency (`useBusinessMoney`, the platform's: its
// country's currency with the decimals the server counts it in, never the browser's Intl, which gives none to the
// forint), written with the platform's `formatMoney`: its thousands grouped from four digits on, as every screen
// writes them. Until the business answers an amount is a dash, never the euro by default nor guessed decimals. A
// supplement shows its sign only when the currency is known, as the till does.
import type { Money } from '../../../../base/frontend/lib/home';
import { formatMoney } from '../../../../base/frontend/lib/money';

export type { Money };
export { formatMoney };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

/** The decimals of an amount while the currency is unknown. */
const UNKNOWN_DECIMALS = 2;

/** The decimals of an amount in `money`; two while it is unknown. */
export const moneyDecimals = (money?: Money): number => money?.decimals ?? UNKNOWN_DECIMALS;

/** A supplement in `money` with its sign («+2,00 zł», «-zł 0.50»; «—» while it is unknown); `''` for none. */
export function formatDelta(cents: number, locale: string, money?: Money): string {
  if (!cents) return '';
  const written = formatMoney(cents, locale, money);
  return cents > 0 && written !== '—' ? `+${written}` : written;
}

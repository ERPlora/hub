// Money of the drawer screens. The server keeps money in whole cents; a person reads it in the page's
// language and types it as she reads it. An amount is written with the platform's `formatMoney` (its thousands
// grouped from four digits on, as every screen writes them); this is the one place the app adds to it what is its
// own (nothing is «—», a note without decimals, a difference with its sign). What is typed in a window is read by the
// platform's money field (`MoneyInput` and its `parseMoney`, `@erplora/ui/components`), as every amount of the Hub
// (hub#1160), and so is what is typed in the list's amount filters (`filterCents`, `amountFilterErrors`; hub#1196).
// The money is the business's (`useBusinessMoney`: its country's currency and the decimals the server counts it
// in): the screens pass it, and until it is known an amount is a figure with two decimals and no symbol, never the
// euro by default. Its decimals come from the server, never from the browser's Intl (which gives none to the forint).

import { formatMoney as writeMoney } from '@erplora/ui/components';

import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { amountFilterErrors, filterCents, useBusinessMoney } from '../../../../base/frontend/lib/money';

const FALLBACK_LOCALE = 'en';
const NO_MONEY_DECIMALS = 2;

const cache = new Map<string, Intl.NumberFormat>();

function formatter(locale: string, key: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const id = `${locale}|${key}`;
  let found = cache.get(id);
  if (!found) {
    try {
      found = new Intl.NumberFormat(locale, options);
    } catch (error) {
      if (!(error instanceof RangeError) || locale === FALLBACK_LOCALE) throw error;
      found = formatter(FALLBACK_LOCALE, key, options);
    }
    cache.set(id, found);
  }
  return found;
}

const missing = (value: unknown): boolean => value === null || value === undefined || Number.isNaN(Number(value));

/** The decimals of `money` (2 in EUR and HUF, 0 in JPY, 3 in KWD): its minor unit; two while unknown. */
export const moneyDecimals = (money?: Money): number => money?.decimals ?? NO_MONEY_DECIMALS;

/** `money`'s currency with `decimals` and the symbol a till there writes («zł», «€»), or a bare figure without it. */
function moneyOptions(money: Money | undefined, decimals: number): Intl.NumberFormatOptions {
  const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: 'always' as const };
  return money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol', ...digits } : digits;
}

/** Minor units as `money` in `locale` («1.150,50 €», «€150.50», «¥5,003»; «—» while the money is unknown);
 *  nothing is «—». */
export function formatMoney(cents: number | null | undefined, locale: string, money?: Money): string {
  return missing(cents) ? '—' : writeMoney(cents, locale, money);
}

/** A note or coin of the count as `money` («500 €», «5.000 Ft», «0,50 €»): a whole face value without decimals (the
 *  old count, Square and Lightspeed), a coin of cents with the currency's own. */
export function formatFace(face: string, locale: string, money?: Money): string {
  const value = Number(face);
  const decimals = Number.isInteger(value) ? 0 : moneyDecimals(money);
  return formatter(locale, `face-${money?.currency ?? ''}-${decimals}`, moneyOptions(money, decimals)).format(value);
}

/** A difference with its sign: «+5,10 €» over, «-4,90 €» short, zero without sign; only a dash without money. */
export function formatSignedMoney(cents: number | null | undefined, locale: string, money?: Money): string {
  if (missing(cents)) return '—';
  const written = formatMoney(cents, locale, money);
  return (cents as number) > 0 && written !== '—' ? `+${written}` : written;
}

/** The text with Intl's no-break spaces as plain ones (what a test or a search compares). */
export function plain(text: string): string {
  return text.replace(/[\u00a0\u202f]/g, ' ');
}

// Numbers of the sale screens: the server keeps money in cents and quantities and percentages as
// decimal strings; a person reads them in the page's language and types amounts. Until
// `@erplora/ui/components/format` has money and number formatters (UI-REQUESTS.md), this is the one
// place the app turns them into text (`Intl.NumberFormat`) and typed amounts into cents.
// The money is the business's (`useBusinessMoney`: its country's currency and the decimals the server counts it in)
// on the till, and a charged sale's own (`moneyOf`) on what it shows or prints: the screens pass it, and until it is
// known an amount is a figure with two decimals and no sign, never the euro by default. Its decimals come from the
// server, never from the browser's Intl (which gives none to the forint).

import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

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

const missing = (value: unknown) => value === null || value === undefined || value === '' || Number.isNaN(Number(value));

/** The decimals of `money` (2 in EUR and HUF, 0 in JPY): its minor unit; two while unknown. */
export const moneyDecimals = (money?: Money): number => money?.decimals ?? NO_MONEY_DECIMALS;

/** The money a charged sale is shown in: its own currency and decimals, as the server sent them; unknown (a figure
 *  without a sign) if a server half way through a deploy does not send them yet. */
export const moneyOf = (sale: { currency: string; currency_decimals: number }): Money | undefined =>
  sale.currency ? { currency: sale.currency, decimals: sale.currency_decimals } : undefined;

// Grouped always: Spanish CLDR waits for five digits (minimumGroupingDigits 2) and would paint «1234,56 €»
// here beside «1.234,56 €» in the other screens (hub#1090).
function moneyOptions(money: Money | undefined, decimals: number): Intl.NumberFormatOptions {
  const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: 'always' } as const;
  return money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol', ...digits } : digits;
}

/** `cents` (minor units) as `money` in `locale` («€1,234.56», «1.234,56 zł», «¥5,003»; «1.234,56» while the
 *  money is unknown); nothing to show is «—». */
export function formatMoney(cents: number | null | undefined, locale: string, money?: Money): string {
  if (missing(cents)) return '—';
  const decimals = moneyDecimals(money);
  return formatter(locale, `money-${money?.currency ?? ''}-${decimals}`, moneyOptions(money, decimals)).format(
    (cents as number) / 10 ** decimals,
  );
}

/** The sign of `money` alone, as a till there writes it («€», «zł», «¥»); nothing while it is unknown. */
export function currencySign(locale: string, money?: Money): string {
  if (!money) return '';
  return (
    formatter(locale, `sign-${money.currency}`, { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol' })
      .formatToParts(0)
      .find((part) => part.type === 'currency')?.value ?? money.currency
  );
}

/** A percentage («21.00» → «21%», «12.50» → «12,5 %»); nothing to show is «—». */
export function formatPercent(value: string | number | null | undefined, locale: string): string {
  if (missing(value)) return '—';
  return formatter(locale, 'percent', { style: 'percent', maximumFractionDigits: 2 }).format(Number(value) / 100);
}

/** A quantity with the decimals it has («0.532» kg → «0,532 kg»); a count of units has no unit. */
export function formatQuantity(value: string | number, unit: string, locale: string): string {
  const number = formatter(locale, 'quantity', { maximumFractionDigits: 3 }).format(Number(value));
  return unit && unit !== 'ud' ? `${number} ${unit}` : number;
}

/** An amount of `money` as typed («12,5», «12.50», 7; «1000» yen) → whole minor units, with at most the decimals
 *  of its currency; blank or not an amount → `undefined`. */
export function centsFromAmount(value: string | number | null | undefined, money?: Money): number | undefined {
  if (value === null || value === undefined) return undefined;
  const text = String(value).trim();
  const decimals = moneyDecimals(money);
  const amount = decimals > 0 ? new RegExp(`^\\d+(?:[.,]\\d{1,${decimals}})?$`) : /^\d+$/;
  if (!text || !amount.test(text)) return undefined;
  return Math.round(Number(text.replace(',', '.')) * 10 ** decimals);
}

/** A day as the reader writes it («14/11/2026», «11/14/2026»); nothing to show is «—». */
export function formatDay(iso: string | null | undefined, locale: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(locale);
}

/** The text with Intl's no-break spaces as plain ones (what a test or a search compares). */
export function plain(text: string): string {
  return text.replace(/[  ]/g, ' ');
}

// How the inventory screens paint money, counts, quantities and rates (pages never format by hand),
// always with the page language's own number format (Intl). Money is whole minor units of the business's money
// (`useBusinessMoney`: its country's currency and the decimals the server counts it in, never the browser's: Intl
// gives the forint none); while it is unknown, a figure without a symbol, never the euro by default. Quantities are
// exact decimals from the API («2.500», at most three decimals): painted ungrouped and without trailing zeros, as
// the server's CSV writes them (queries.quantity_text).
import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

const NO_MONEY_DECIMALS = 2;

const formats = new Map<string, Intl.NumberFormat>();
const decimalMarks = new Map<string, string>();

/** The decimals of `money` (2 in EUR and HUF, 0 in JPY): its minor unit; two while unknown. */
export const moneyDecimals = (money?: Money): number => money?.decimals ?? NO_MONEY_DECIMALS;

function moneyFormat(locale: string, money: Money | undefined): Intl.NumberFormat {
  const decimals = moneyDecimals(money);
  const key = `${locale}|money|${money?.currency ?? ''}|${decimals}`;
  let found = formats.get(key);
  if (!found) {
    const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
    found = new Intl.NumberFormat(locale, money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol', ...digits } : digits);
    formats.set(key, found);
  }
  return found;
}

function numberFormat(locale: string, kind: 'count' | 'quantity' | 'percent'): Intl.NumberFormat {
  const key = `${locale}|${kind}`;
  let found = formats.get(key);
  if (!found) {
    const options: Record<typeof kind, Intl.NumberFormatOptions> = {
      count: {},
      quantity: { maximumFractionDigits: 3, useGrouping: false },
      percent: { style: 'percent', maximumFractionDigits: 2 },
    };
    found = new Intl.NumberFormat(locale, options[kind]);
    formats.set(key, found);
  }
  return found;
}

/** The decimal mark of `locale` («,» in Spanish, «.» in English). */
export function decimalMark(locale: string): string {
  let found = decimalMarks.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';
    decimalMarks.set(locale, found);
  }
  return found;
}

/** Whole minor units as `money` in `locale` («2,20 €», «€2.20», «zł 12.50», «¥1,210»; «12,50» while the money is
 *  unknown), with the symbol a till there writes. */
export function formatMoney(cents: number, locale: string, money?: Money): string {
  return moneyFormat(locale, money).format(cents / 10 ** moneyDecimals(money));
}

/** A count («12.345» products in Spanish). */
export function formatCount(value: number, locale: string): string {
  return numberFormat(locale, 'count').format(value);
}

/** An exact decimal as the person reads it: «2.500» → «2,5» (es), «3.000» → «3»; a non-figure as it came. */
export function formatQuantity(value: string | number, locale: string): string {
  const text = String(value).trim();
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text;
  // `+ 0` turns a negative zero («-0.000») into 0.
  return numberFormat(locale, 'quantity').format(Number(text) + 0);
}

/** A movement's quantity with its sign: «+2» in, «-1,5» out, «0». */
export function formatSignedQuantity(value: string | number, locale: string): string {
  const painted = formatQuantity(value, locale);
  return /^\d/.test(painted) && painted !== '0' ? `+${painted}` : painted;
}

/** A tax rate in % («21.00») as the language writes it: «21 %» (es), «21%» (en). */
export function formatPercent(rate: string | number, locale: string): string {
  return numberFormat(locale, 'percent').format(Number(rate) / 100);
}

/** The ledger's date as the page language writes it short: numeric day, month and year, and the time
 *  («7/3/25, 9:05»), so a tablet column keeps the time of day (inventory#130, #139). `timeZone`: the
 *  page's when not given. Not a date: the text as it came. */
export function formatShortDateTime(value: string, locale: string, timeZone?: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short', timeZone }).format(date);
}

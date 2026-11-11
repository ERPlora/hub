// How the inventory screens paint money, counts, quantities and rates (pages never format by hand),
// always with the page language's own number format (Intl). Money is whole minor units of the business's money
// (`useBusinessMoney`: its country's currency and the decimals the server counts it in, never the browser's: Intl
// gives the forint none), written with the platform's `formatMoney`: its thousands grouped from four digits on, as
// every screen writes them; while it is unknown, an amount is a dash, never the euro by default nor guessed decimals. Quantities are
// exact decimals from the API («2.500», at most three decimals), written with the platform's `formatQuantity`: without
// trailing zeros and grouped from four digits on («12.500»), as the till and the invoice write them (hub#974).
import { formatQuantity } from '@erplora/ui/components';

import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { formatMoney, useBusinessMoney } from '../../../../base/frontend/lib/money';
export { formatQuantity };

const formats = new Map<string, Intl.NumberFormat>();

function numberFormat(locale: string, kind: 'count' | 'percent'): Intl.NumberFormat {
  const key = `${locale}|${kind}`;
  let found = formats.get(key);
  if (!found) {
    const options: Record<typeof kind, Intl.NumberFormatOptions> = {
      count: {},
      percent: { style: 'percent', maximumFractionDigits: 2 },
    };
    found = new Intl.NumberFormat(locale, options[kind]);
    formats.set(key, found);
  }
  return found;
}

/** A count («12.345» products in Spanish). */
export function formatCount(value: number, locale: string): string {
  return numberFormat(locale, 'count').format(value);
}

/** A movement's quantity with its sign: «+2» in, «-1,5» out, «0», «+1.500». */
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

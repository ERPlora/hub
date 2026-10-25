// Numbers and days of the invoice screens: the server keeps money in signed cents, quantities and rates as
// decimal strings and days as `YYYY-MM-DD`; a person reads them in the page's language and types amounts.
// Until `@erplora/ui/components/format` has money and number formatters (UI-REQUESTS.md), this is the one
// place the app turns them into text (`Intl`) and amounts into cents. Money is in the invoice's own currency (the
// business's when it was issued), with the decimals the server counts it in (`currency_decimals`; the browser's
// Intl gives the forint none): without one, a figure without a symbol, never the euro by default.
import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };

const FALLBACK_LOCALE = 'en';
const NO_MONEY_DECIMALS = 2;
const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

const cache = new Map<string, Intl.NumberFormat | Intl.DateTimeFormat>();

function cached<T extends Intl.NumberFormat | Intl.DateTimeFormat>(id: string, make: () => T): T {
  let found = cache.get(id) as T | undefined;
  if (!found) {
    found = make();
    cache.set(id, found);
  }
  return found;
}

function numberFormat(locale: string, key: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  return cached(`n|${locale}|${key}`, () => {
    try {
      return new Intl.NumberFormat(locale, options);
    } catch (error) {
      if (!(error instanceof RangeError) || locale === FALLBACK_LOCALE) throw error;
      return numberFormat(FALLBACK_LOCALE, key, options);
    }
  });
}

const missing = (value: unknown) => value === null || value === undefined || value === '' || Number.isNaN(Number(value));

/** The money of an invoice: its currency and the decimals the server counts it in. */
export const moneyOf = (invoice: { currency: string; currency_decimals: number }): Money => ({
  currency: invoice.currency,
  decimals: invoice.currency_decimals,
});

/** `money`'s currency from `min` to `max` decimals, grouped, with the symbol a till there writes («zł», «€»); a
 *  figure without a symbol while there is no money. */
function moneyFormat(locale: string, money: Money | undefined, min: number, max: number): Intl.NumberFormat {
  const digits = { minimumFractionDigits: min, maximumFractionDigits: max, useGrouping: 'always' as const };
  const options: Intl.NumberFormatOptions = money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol', ...digits } : digits;
  return numberFormat(locale, `money-${money?.currency ?? ''}-${min}-${max}`, options);
}

// Grouped always: Spanish CLDR waits for five digits (minimumGroupingDigits 2) and would paint «1234,56 €»
// here beside «1.234,56 €» in the other screens (hub#1090).
/** `cents` (minor units) as `money` in `locale` («€1,234.56», «1.234,56 €», «zł 121.00», «¥12,100»); nothing to
 *  show is «—». */
export function formatMoney(cents: number | null | undefined, locale: string, money?: Money): string {
  if (missing(cents)) return '—';
  const decimals = money?.decimals ?? NO_MONEY_DECIMALS;
  return moneyFormat(locale, money, decimals, decimals).format((cents as number) / 10 ** decimals);
}

/** A unit price in cents with two decimals («82.64» → «€0.8264»): the decimals of `money`, up to two more when
 *  the price without VAT has them (RD 1619/2012 art. 6.1.f), thousands grouped as `formatMoney`'s; nothing to
 *  show is «—». */
export function formatUnitPrice(cents: string | number | null | undefined, locale: string, money?: Money): string {
  if (missing(cents)) return '—';
  const decimals = money?.decimals ?? NO_MONEY_DECIMALS;
  return moneyFormat(locale, money, decimals, decimals + 2).format(Number(cents) / 10 ** decimals);
}

/** A rate («21.00» → «21%», «5.20» → «5,2 %»); nothing to show is «—». */
export function formatPercent(value: string | number | null | undefined, locale: string): string {
  if (missing(value)) return '—';
  return numberFormat(locale, 'percent', { style: 'percent', maximumFractionDigits: 2 }).format(Number(value) / 100);
}

/** A quantity with the decimals it has («2.000» → «2», «0.532» → «0,532»), its sign included. */
export function formatQuantity(value: string | number, locale: string): string {
  return numberFormat(locale, 'quantity', { maximumFractionDigits: 3 }).format(Number(value));
}

/** A rate of the server as a person types it («7.00» → «7», «9.50» → «9,5» in Spanish); none is blank. */
export function typedRate(value: string | null, locale: string): string {
  if (missing(value)) return '';
  return numberFormat(locale, 'typed-rate', { maximumFractionDigits: 2, useGrouping: false }).format(Number(value));
}

/** A calendar day («2026-09-29» → «29/9/2026» in Spanish), built from its parts and formatted in UTC so no
 *  clock moves it to the day before; not a day is shown as it came, nothing is «—». */
export function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return '—';
  const parts = DAY.exec(value);
  if (!parts) return value;
  const day = new Date(Date.UTC(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3])));
  const format = cached(`d|${locale}`, () => {
    try {
      return new Intl.DateTimeFormat(locale, { timeZone: 'UTC' });
    } catch {
      return new Intl.DateTimeFormat(FALLBACK_LOCALE, { timeZone: 'UTC' });
    }
  });
  return format.format(day);
}

const AMOUNT = /^\d+(?:[.,]\d{1,2})?$/;

/** An amount as typed («12,5», «12.50», 7) → whole cents; blank, negative or not an amount → `undefined`. */
export function centsFromAmount(value: string | number | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined;
  const text = String(value).trim();
  if (!text || !AMOUNT.test(text)) return undefined;
  return Math.round(Number(text.replace(',', '.')) * 100);
}

/** The text with Intl's no-break spaces as plain ones (what a test or a search compares). */
export function plain(text: string): string {
  return text.replace(/[  ]/g, ' ');
}

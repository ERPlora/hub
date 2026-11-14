// Numbers and days of the VeriFactu screens: the server keeps money in signed cents, quantities and rates as
// decimal strings and days as `YYYY-MM-DD`; a person reads them in the page's language.
// Until `@erplora/ui/components/format` has money and number formatters (UI-REQUESTS.md), this is the one
// place the app turns them into text (`Intl`). An amount typed in a filter is read by the platform, as every amount
// filter of the Hub (`filterCents`, `amountFilterErrors`). No screen of the app writes a quantity: where
// one is shown, it is the platform's `formatQuantity` of `@erplora/ui/components` (hub#974).
export type { Money } from '../../../../base/frontend/lib/home';
export { amountFilterErrors, filterCents, useBusinessMoney } from '../../../../base/frontend/lib/money';

const CURRENCY = 'EUR';
const FALLBACK_LOCALE = 'en';
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

// Grouped always: Spanish CLDR waits for five digits (minimumGroupingDigits 2) and would paint «1234,56 €»
// here beside «1.234,56 €» in the other screens.
/** `cents` as euros in `locale` («€1,234.56», «1.234,56 €», «-12,10 €»); nothing to show is «—». */
export function formatMoney(cents: number | null | undefined, locale: string): string {
  if (missing(cents)) return '—';
  return numberFormat(locale, 'money', { style: 'currency', currency: CURRENCY, useGrouping: 'always' }).format((cents as number) / 100);
}

/** A unit price in cents with two decimals («82.64» → «€0.8264»): two decimals of euro, up to four when
 *  the price without VAT has them (RD 1619/2012 art. 6.1.f), thousands grouped as `formatMoney`'s; nothing to
 *  show is «—». */
export function formatUnitPrice(cents: string | number | null | undefined, locale: string): string {
  if (missing(cents)) return '—';
  return numberFormat(locale, 'unit-price', {
    style: 'currency',
    currency: CURRENCY,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
    useGrouping: 'always',
  }).format(
    Number(cents) / 100,
  );
}

/** A rate («21.00» → «21%», «5.20» → «5,2 %»); nothing to show is «—». */
export function formatPercent(value: string | number | null | undefined, locale: string): string {
  if (missing(value)) return '—';
  return numberFormat(locale, 'percent', { style: 'percent', maximumFractionDigits: 2 }).format(Number(value) / 100);
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

/** The text with Intl's no-break spaces as plain ones (what a test or a search compares). */
export function plain(text: string): string {
  return text.replace(/[  ]/g, ' ');
}

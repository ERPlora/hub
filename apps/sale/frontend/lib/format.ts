// Numbers of the sale screens: the server keeps money in cents and quantities and percentages as
// decimal strings; a person reads them in the page's language and types euros. Until
// `@erplora/ui/components/format` has money and number formatters (UI-REQUESTS.md), this is the one
// place the app turns them into text (`Intl.NumberFormat`) and euros into cents.

const CURRENCY = 'EUR';
const FALLBACK_LOCALE = 'en';

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

/** `cents` as euros in `locale` («€1,234.56», «1234,56 €»); nothing to show is «—». */
export function formatMoney(cents: number | null | undefined, locale: string): string {
  if (missing(cents)) return '—';
  return formatter(locale, 'money', { style: 'currency', currency: CURRENCY }).format((cents as number) / 100);
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

const AMOUNT = /^\d+(?:[.,]\d{1,2})?$/;

/** Euros as typed («12,5», «12.50», 7) → whole cents; blank or not an amount → `undefined`. */
export function centsFromEuros(value: string | number | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined;
  const text = String(value).trim();
  if (!text || !AMOUNT.test(text)) return undefined;
  return Math.round(Number(text.replace(',', '.')) * 100);
}

/** The text with Intl's no-break spaces as plain ones (what a test or a search compares). */
export function plain(text: string): string {
  return text.replace(/[  ]/g, ' ');
}

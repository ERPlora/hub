// Money of the customer screens: the server keeps cents (WORKBOOK «Reglas que no se rompen»), a
// person reads and types euros. Until `@erplora/ui/components/format` has a money formatter
// (UI-REQUESTS.md), this is the one place the app turns cents into text and euros into cents.

const CURRENCY = 'EUR';
const FALLBACK_LOCALE = 'en';

const formatters = new Map<string, Intl.NumberFormat>();

function formatter(locale: string): Intl.NumberFormat {
  let found = formatters.get(locale);
  if (!found) {
    try {
      found = new Intl.NumberFormat(locale, { style: 'currency', currency: CURRENCY });
    } catch (error) {
      if (!(error instanceof RangeError) || locale === FALLBACK_LOCALE) throw error;
      found = formatter(FALLBACK_LOCALE);
    }
    formatters.set(locale, found);
  }
  return found;
}

/** `cents` as euros in `locale` («€1,234.56», «1234,56 €»); nothing to show is «—». */
export function formatMoney(cents: number | null | undefined, locale: string): string {
  if (cents === null || cents === undefined || Number.isNaN(cents)) return '—';
  return formatter(locale).format(cents / 100);
}

/** What an amount typed by a person says. */
export type EurosReading = { kind: 'blank' } | { kind: 'invalid' } | { kind: 'amount'; cents: number };

const GROUPED = (separator: string) => new RegExp(`^\\d{1,3}(?:\\${separator}\\d{3})+$`);

/** The whole euros of `integer` written with `group` as thousands separator, or `null`. */
function wholeEuros(integer: string, group: string | null): number | null {
  if (/^\d+$/.test(integer)) return Number(integer);
  if (group && GROUPED(group).test(integer)) return Number(integer.split(group).join(''));
  return null;
}

/**
 * Euros as a person types them, in either convention: «1.000», «1.000,50», «1,000.50», «12,5»,
 * «2 500». A separator followed by exactly three digits groups thousands (cents have two); with both,
 * the last one is the decimal one. Negative or anything else is not an amount.
 */
export function readEuros(value: string | number | null | undefined): EurosReading {
  if (value === null || value === undefined) return { kind: 'blank' };
  const text = String(value).replace(/[\s\u00a0\u202f]/g, '');
  if (!text) return { kind: 'blank' };
  if (!/^\d[\d.,]*$/.test(text)) return { kind: 'invalid' };
  const lastDot = text.lastIndexOf('.');
  const lastComma = text.lastIndexOf(',');
  let euros: number | null;
  let cents = 0;
  if (lastDot >= 0 && lastComma >= 0) {
    const decimal = lastDot > lastComma ? '.' : ',';
    const group = decimal === '.' ? ',' : '.';
    const at = text.lastIndexOf(decimal);
    const fraction = text.slice(at + 1);
    if (!/^\d{1,2}$/.test(fraction)) return { kind: 'invalid' };
    euros = wholeEuros(text.slice(0, at), group);
    cents = Math.round(Number(`0.${fraction}`) * 100);
  } else if (lastDot >= 0 || lastComma >= 0) {
    const separator = lastDot >= 0 ? '.' : ',';
    const parts = text.split(separator);
    const tail = parts[parts.length - 1];
    if (parts.length === 2 && /^\d{1,2}$/.test(tail)) {
      euros = wholeEuros(parts[0], null);
      cents = Math.round(Number(`0.${tail}`) * 100);
    } else {
      euros = wholeEuros(text, separator);
    }
  } else {
    euros = wholeEuros(text, null);
  }
  return euros === null ? { kind: 'invalid' } : { kind: 'amount', cents: euros * 100 + cents };
}

/** Euros as typed → whole cents; blank or not an amount → no bound. */
export function centsFromEuros(value: string | number | null | undefined): number | undefined {
  const reading = readEuros(value);
  return reading.kind === 'amount' ? reading.cents : undefined;
}

// How the pricing screens paint money, quantities, percents and days (pages never format by hand), always
// with the page language's own format (Intl). Money is whole cents of the list's currency (euros unless
// it says another; every currency of a list has two decimals, as the server checks). A day is a calendar
// day (`YYYY-MM-DD`), painted as it is whatever the device's time zone.
type Translate = (key: string, named?: Record<string, unknown>) => string;

/** The currency the business sells in (phase 1: euros, as the server's `BUSINESS_CURRENCY`). */
export const BUSINESS_CURRENCY = 'EUR';

const formats = new Map<string, Intl.NumberFormat>();
const days = new Map<string, Intl.DateTimeFormat>();
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

function numberFormat(locale: string, key: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const cacheKey = `${locale}|${key}`;
  let found = formats.get(cacheKey);
  if (!found) {
    found = new Intl.NumberFormat(locale, options);
    formats.set(cacheKey, found);
  }
  return found;
}

/** Whole cents in `currency` (euros by default), in `locale` («12,50 €», «€12.50», «$12.50»), with the
 *  thousands grouped from four digits on in every language (Spanish CLDR waits for five: hub#1090). */
export function formatMoney(cents: number, locale: string, currency = 'EUR'): string {
  return numberFormat(locale, `money:${currency}`, { style: 'currency', currency, useGrouping: 'always' }).format(cents / 100);
}

/** A quantity as the server sends it («10.000») without its trailing zeros, in `locale`. */
export function formatQuantity(value: string | number, locale: string): string {
  return numberFormat(locale, 'quantity', { maximumFractionDigits: 3 }).format(Number(value));
}

/** A percent as the server sends it («12.50»), with up to two decimals, in `locale` («12,5 %»). */
export function formatPercent(value: string | number, locale: string): string {
  return numberFormat(locale, 'percent', { style: 'percent', maximumFractionDigits: 2 }).format(Number(value) / 100);
}

/** A calendar day (`YYYY-MM-DD`) in `locale` («1 jul 2026», «Jul 1, 2026»); `''` for none. */
export function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return '';
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  let found = days.get(locale);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' });
    days.set(locale, found);
  }
  return found.format(new Date(Date.UTC(year, month - 1, day)));
}

/** «Always», «From …», «Until …» or «… – …» of a list or a rule. */
export function validityLabel(from: string | null, until: string | null, t: Translate, locale: string): string {
  if (from && until) return t('pricing.validity.between', { from: formatDate(from, locale), until: formatDate(until, locale) });
  if (from) return t('pricing.validity.from', { from: formatDate(from, locale) });
  if (until) return t('pricing.validity.until', { until: formatDate(until, locale) });
  return t('pricing.validity.always');
}

/** What a decimal field holds, with a comma or a point, as the server reads it («0,5» → «0.5»);
 *  `null` when it is empty, negative or has more than `places` decimals. */
export function readDecimal(text: string, places: number): string | null {
  const raw = text.trim().replace(',', '.');
  if (!new RegExp(`^\\d+(\\.\\d{1,${places}})?$`).test(raw)) return null;
  return raw;
}

/** A quantity as its field shows it: the page's decimal mark, no grouping, no trailing zeros. */
export function quantityFieldText(value: string, locale: string): string {
  const plain = String(Number(value));
  return plain.replace('.', decimalMark(locale));
}

// How the service screens paint money, discounts and days (pages never format by hand), always with the
// page language's own format (Intl). Money is whole cents of euros: the Hub has no currency setting and
// every ERPlora business invoices in euros. A percentage discount travels in basis points (1050 =
// 10,50 %): the form writes and reads it as a percentage with at most two decimals.

const CURRENCY = 'EUR';

const formats = new Map<string, Intl.NumberFormat>();
const days = new Map<string, Intl.DateTimeFormat>();
const decimalMarks = new Map<string, string>();

function numberFormat(locale: string, kind: 'money' | 'percent' | 'plain'): Intl.NumberFormat {
  const key = `${locale}|${kind}`;
  let found = formats.get(key);
  if (!found) {
    const options: Record<typeof kind, Intl.NumberFormatOptions> = {
      money: { style: 'currency', currency: CURRENCY },
      percent: { style: 'percent', maximumFractionDigits: 2 },
      plain: { maximumFractionDigits: 2, useGrouping: false },
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

/** Whole cents as euros in `locale` («22,50 €», «€22.50»). */
export function formatMoney(cents: number, locale: string): string {
  return numberFormat(locale, 'money').format(cents / 100);
}

/** Basis points as a percentage in `locale` («10,5 %», «10.5%»). */
export function formatPercentBp(bp: number, locale: string): string {
  return numberFormat(locale, 'percent').format(bp / 10000);
}

/** Basis points for a percentage field, in the page format, ungrouped («10,5»). */
export function percentFieldText(bp: number, locale: string): string {
  return numberFormat(locale, 'plain').format(bp / 100);
}

/** What a percentage field holds, in basis points (empty = 0); `null` when it is not 0–100 with ≤ 2 decimals. */
export function readPercentBp(text: string): number | null {
  const raw = text.replace(/[%\s]/g, '').replace(',', '.');
  if (raw === '') return 0;
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(raw)) return null;
  const bp = Math.round(Number(raw) * 100);
  return bp <= 10000 ? bp : null;
}

/** The day of a moment in `locale` («13 oct 2026», «Oct 13, 2026»); `''` for nothing. */
export function formatDate(value: string | null | undefined, locale: string, timeZone?: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const key = `${locale}|${timeZone ?? ''}`;
  let found = days.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone });
    days.set(key, found);
  }
  return found.format(date);
}

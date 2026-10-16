// How the payment screens paint money, days and statuses (pages never format by hand), always in the
// page language's own format (Intl). An amount is whole minor units of the payment's own currency: its
// scale comes from Intl (2 decimals in EUR, 0 in JPY, 3 in KWD). A payment date is a calendar day
// (`YYYY-MM-DD`), painted in UTC so the browser's time zone never moves it a day.
import type { StatusPillTone } from '@erplora/ui/components';

import type { PaymentStatus } from '../operations';

/** The business's currency until the Hub keeps its own (the server's `business_currency()`). */
export const CURRENCY = 'EUR';

const money = new Map<string, Intl.NumberFormat>();
const days = new Map<string, Intl.DateTimeFormat>();
const decimalMarks = new Map<string, string>();

function moneyFormat(locale: string, currency: string): Intl.NumberFormat {
  const key = `${locale}|${currency}`;
  let found = money.get(key);
  if (!found) {
    found = new Intl.NumberFormat(locale, { style: 'currency', currency });
    money.set(key, found);
  }
  return found;
}

/** Whole minor units of `currency` in `locale` («12,50 €», «€12.50», «¥1,999»). */
export function formatMoney(minor: number, locale: string, currency: string = CURRENCY): string {
  const format = moneyFormat(locale, currency);
  const decimals = format.resolvedOptions().maximumFractionDigits ?? 2;
  return format.format(minor / 10 ** decimals);
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

/** A calendar day (or the date half of a moment) as `locale` writes it («13/07/2026»); anything else as is. */
export function formatDay(value: string | null | undefined, locale: string): string {
  const raw = value ?? '';
  const iso = raw.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return raw;
  const date = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return raw;
  let found = days.get(locale);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' });
    days.set(locale, found);
  }
  return found.format(date);
}

/** The device's own day as `YYYY-MM-DD` (a date field's value), never the UTC one. */
export function localDay(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** The tone of each status's pill: inert, in progress, waiting on the bank, done, stopped. */
export const STATUS_TONE: Readonly<Record<PaymentStatus, StatusPillTone>> = Object.freeze({
  draft: 'neutral',
  approved: 'info',
  sent: 'warning',
  completed: 'success',
  cancelled: 'danger',
});

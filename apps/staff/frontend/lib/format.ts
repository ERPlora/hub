// How the staff screens paint and read money, rates, calendar dates and wall-clock times (pages never
// format by hand). Money is whole cents of euros: the Hub has no currency setting yet and every
// ERPlora business invoices in euros. A calendar date (`YYYY-MM-DD`: a hire date, an absence, a
// schedule's validity) is a day, not an instant: painted in UTC so it never moves a day. A time is the
// business's wall clock: `HH:MM:SS` on the wire, `HH:MM` on screen and in a time field.

const CURRENCY = 'EUR';
const DASH = '—';

const moneyFormats = new Map<string, Intl.NumberFormat>();
const dateFormats = new Map<string, Intl.DateTimeFormat>();

function moneyFormat(locale: string): Intl.NumberFormat {
  let found = moneyFormats.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale, { style: 'currency', currency: CURRENCY });
    moneyFormats.set(locale, found);
  }
  return found;
}

function decimalMark(locale: string): string {
  return new Intl.NumberFormat(locale).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';
}

/** Whole cents as euros in `locale` («12,50 €», «€12.50»). */
export function formatMoney(cents: number, locale: string): string {
  return moneyFormat(locale).format(cents / 100);
}

/** Whole cents as the figure a person types in a money field («12,50» in Spanish, «12.50» in English). */
export function moneyText(cents: number, locale: string): string {
  return (cents / 100).toFixed(2).replace('.', decimalMark(locale));
}

/**
 * A money field back to whole cents: a comma or a point marks the decimals; empty is 0 (no rate).
 * `null` when it is not a figure (grouped thousands included: «1.250,50» is ambiguous, and the server
 * takes cents, so the person is asked to write the figure plainly). The sign is kept: the server
 * refuses a negative rate under its field.
 */
export function centsFromText(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === '') return 0;
  if (!/^-?\d+(?:[.,]\d+)?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed.replace(',', '.')) * 100);
}

/** A percentage from the API («12.50») without trailing zeros, in the reader's decimal mark: «12,5 %». */
export function formatPercent(value: string | number, locale: string): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(number)} %`;
}

function dateFormat(locale: string): Intl.DateTimeFormat {
  let found = dateFormats.get(locale);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' });
    dateFormats.set(locale, found);
  }
  return found;
}

/** A calendar day (`YYYY-MM-DD`) in the reader's order (`05/10/2026` in Spanish, `10/05/2026` in English). */
export function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return DASH;
  const iso = value.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return value;
  const date = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : dateFormat(locale).format(date);
}

/** A wall-clock time as `HH:MM` («09:00:00» → «09:00»); nothing is `''`. */
export function formatTime(value: string | null | undefined): string {
  return value ? value.slice(0, 5) : '';
}

/** What a time field (`type="time"`) holds for a value of the API: `HH:MM`, or `''`. */
export const timeValue = formatTime;

/** A working day as the API gives it. */
export interface DaySpan {
  weekday: number;
  start_time: string;
  end_time: string;
  break_start: string | null;
  break_end: string | null;
}

/** The week at a glance: «Mon 09:00–18:00 (13:00–14:00) · Wed 10:00–16:00»; no day, a dash. */
export function hoursSummary(days: readonly DaySpan[], dayLabel: (weekday: number) => string): string {
  if (!days.length) return DASH;
  return [...days]
    .sort((a, b) => a.weekday - b.weekday)
    .map((day) => {
      const pause = day.break_start && day.break_end ? ` (${formatTime(day.break_start)}–${formatTime(day.break_end)})` : '';
      return `${dayLabel(day.weekday)} ${formatTime(day.start_time)}–${formatTime(day.end_time)}${pause}`;
    })
    .join(' · ');
}

// How the staff screens paint and read money, rates, calendar dates and wall-clock times (pages never
// format by hand). Money is whole minor units of the business's currency (`useBusinessMoney`, the
// platform's: its country's currency with the decimals the server counts it in, never the browser's Intl,
// which gives none to the forint). Until the business answers an amount is a figure without a symbol and
// two decimals, never the euro by default. A calendar date (`YYYY-MM-DD`: a hire date, an absence, a
// schedule's validity) is a day, not an instant: painted in UTC so it never moves a day. A time is the
// business's wall clock: `HH:MM:SS` on the wire, `HH:MM` on screen and in a time field.
import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

const DASH = '—';
/** The decimals of an amount while the currency is unknown. */
const UNKNOWN_DECIMALS = 2;

const moneyFormats = new Map<string, Intl.NumberFormat>();
const dateFormats = new Map<string, Intl.DateTimeFormat>();

/** The decimals of an amount in `money`; two while it is unknown. */
const moneyDecimals = (money?: Money): number => money?.decimals ?? UNKNOWN_DECIMALS;

function moneyFormat(locale: string, money: Money | undefined): Intl.NumberFormat {
  const decimals = moneyDecimals(money);
  const key = `${locale}|${money?.currency ?? ''}|${decimals}`;
  let found = moneyFormats.get(key);
  if (!found) {
    const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
    // The symbol a till of that country prints («zł», «¥»); until the business is known, the figure alone.
    const style: Intl.NumberFormatOptions = money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol' } : {};
    found = new Intl.NumberFormat(locale, { ...style, ...digits });
    moneyFormats.set(key, found);
  }
  return found;
}

function decimalMark(locale: string): string {
  return new Intl.NumberFormat(locale).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';
}

/** Minor units in `money`, in `locale` («12,50 €», «12,50 zł», «¥1,500»; «12,50» while it is unknown). */
export function formatMoney(cents: number, locale: string, money?: Money): string {
  return moneyFormat(locale, money).format(cents / 10 ** moneyDecimals(money));
}

/** The symbol of `money` a till of that country prints («€», «zł», «¥»); `''` while it is unknown. */
export function currencySymbol(locale: string, money?: Money): string {
  if (!money) return '';
  return moneyFormat(locale, money).formatToParts(0).find((part) => part.type === 'currency')?.value ?? money.currency;
}

/** Minor units as the figure a person types in a money field, with the decimals of `money` («12,50» in
 *  Spanish, «12.50» in English; «1500» in yen). */
export function moneyText(cents: number, locale: string, money?: Money): string {
  const decimals = moneyDecimals(money);
  return (cents / 10 ** decimals).toFixed(decimals).replace('.', decimalMark(locale));
}

/**
 * A money field back to whole minor units of `money`: a comma or a point marks the decimals, rounded to the
 * currency's (none in yen); empty is 0 (no rate). `null` when it is not a figure (grouped thousands
 * included: «1.250,50» is ambiguous, and the server takes minor units, so the person is asked to write the
 * figure plainly). The sign is kept: the server refuses a negative rate under its field.
 */
export function centsFromText(text: string, money?: Money): number | null {
  const trimmed = text.trim();
  if (trimmed === '') return 0;
  if (!/^-?\d+(?:[.,]\d+)?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed.replace(',', '.')) * 10 ** moneyDecimals(money));
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

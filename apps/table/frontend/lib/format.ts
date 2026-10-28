// How the table screens paint times, durations and money (pages never format by hand): the business's
// clock (its IANA zone, `table.settings.get` → `timezone`), the page language's own format (Intl), and
// the tone of an open check's time after the room settings' minutes (amber, then red; Square paints the
// same two). Money is whole minor units, as Sales charges it: what a check charged in the currency it was
// charged in (a record is never rewritten), the lines of an open check in the business's (`useBusinessMoney`,
// the platform's: its country's), with the decimals the server counts, never the browser's Intl (which gives
// the forint none). Until the business answers an amount is a figure without a symbol, never the euro by default.
import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

/** The decimals of an amount while its currency is unknown. */
const UNKNOWN_DECIMALS = 2;
const MINUTE = 60_000;

const formats = new Map<string, Intl.DateTimeFormat>();

function dateFormat(locale: string, timeZone: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale}|${timeZone}|${JSON.stringify(options)}`;
  let found = formats.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { ...options, timeZone });
    formats.set(key, found);
  }
  return found;
}

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Whole minutes from `iso` to `now`, never below zero; `null` without a usable moment. */
export function minutesSince(iso: string | null | undefined, now: Date): number | null {
  const from = parse(iso);
  if (!from) return null;
  return Math.max(0, Math.floor((now.getTime() - from.getTime()) / MINUTE));
}

/** Whole minutes a check lasted: until its close, or until now while it is open. */
export function durationMinutes(openedAt: string, closedAt: string | null, now: Date): number {
  const until = parse(closedAt) ?? now;
  const from = parse(openedAt);
  if (!from) return 0;
  return Math.max(0, Math.floor((until.getTime() - from.getTime()) / MINUTE));
}

export type DurationTone = 'ok' | 'warning' | 'critical';

/** Only an OPEN check is an alarm: amber from the warning minutes, red from the critical ones. */
export function durationTone(
  status: string,
  minutes: number,
  room: { timer_warning_minutes: number; timer_critical_minutes: number },
): DurationTone {
  if (status !== 'open') return 'ok';
  if (minutes >= room.timer_critical_minutes) return 'critical';
  if (minutes >= room.timer_warning_minutes) return 'warning';
  return 'ok';
}

/** The business wall clock of `iso` («21:00», «9:00 PM»); '' without a moment. */
export function clock(iso: string | null | undefined, locale: string, timeZone: string): string {
  const date = parse(iso);
  if (!date) return '';
  return dateFormat(locale, timeZone, { hour: 'numeric', minute: '2-digit' }).format(date);
}

/** A moment of the list of checks: the time on the business's today, else its day and time (and its
 *  year when another one): «Closed» and «All» are not limited to tonight. '—' without one. */
export function clockTime(iso: string | null | undefined, now: Date, locale: string, timeZone: string): string {
  const date = parse(iso);
  if (!date) return '—';
  const dayOf = (moment: Date) => dateFormat('en-CA', timeZone, { year: 'numeric', month: '2-digit', day: '2-digit' }).format(moment);
  const day = dayOf(date);
  const today = dayOf(now);
  if (day === today) return clock(iso, locale, timeZone);
  const options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' };
  if (day.slice(0, 4) !== today.slice(0, 4)) options.year = 'numeric';
  return dateFormat(locale, timeZone, options).format(date);
}

const moneyFormats = new Map<string, Intl.NumberFormat>();

/** Minor units in `money`, in `locale` («42,50 zł», «€22.50», «¥1,250»; «22,50» while it is unknown); nothing
 *  charged is '—', never zero. */
export function formatMoney(cents: number | null | undefined, locale: string, money?: Money): string {
  if (cents === null || cents === undefined) return '—';
  const decimals = money?.decimals ?? UNKNOWN_DECIMALS;
  const key = `${locale}|${money?.currency ?? ''}|${decimals}`;
  let found = moneyFormats.get(key);
  if (!found) {
    const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
    // The symbol a till of that country prints («zł», «¥»); until the currency is known, the figure alone.
    const style: Intl.NumberFormatOptions = money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol' } : {};
    found = new Intl.NumberFormat(locale, { ...style, ...digits });
    moneyFormats.set(key, found);
  }
  return found.format(cents / 10 ** decimals);
}

/** The money of a charge: the currency it was charged in, with the decimals the server says, else `business`'s. */
export function recordMoney(record: { currency?: string | null; currency_decimals?: number | null }, business?: Money): Money | undefined {
  const { currency, currency_decimals: decimals } = record;
  return currency && typeof decimals === 'number' ? { currency, decimals } : business;
}

// The days and moments a panel of the Home shows, in the person's language and time zone.
import { formatDateTime } from '@erplora/ui/components';

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
export const DAY_MS = 86_400_000;

/** A civil day `YYYY-MM-DD` (a business day has no zone) as its UTC midnight, always formatted in UTC so it never
 *  moves to the day before or after; an instant or a day the calendar does not have is no day. */
export function isoDay(value: string): Date | undefined {
  const match = ISO_DAY.exec(value);
  if (!match) return undefined;
  const [year, month, day] = match.slice(1).map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const same = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return same ? date : undefined;
}

export type DayStyle = 'weekday' | 'date' | 'full';

const DAY_STYLES: Record<DayStyle, Intl.DateTimeFormatOptions> = {
  weekday: { weekday: 'short' },
  date: { day: 'numeric', month: 'short' },
  full: { weekday: 'short', day: 'numeric', month: 'short' },
};

const dayFormats = new Map<string, Intl.DateTimeFormat>();

/** A day of `isoDay` in the person's language: «vie» / «Fri», «23 oct» / «Oct 23», «vie, 23 oct» / «Fri, Oct 23». */
export function formatDay(day: Date, style: DayStyle, locale: string): string {
  const id = `${locale}|${style}`;
  let found = dayFormats.get(id);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { ...DAY_STYLES[style], timeZone: 'UTC' });
    dayFormats.set(id, found);
  }
  return found.format(day);
}

/** When a moment is read: «now» and the IANA time zone (the device's when omitted; tests pin both). */
export interface MomentOptions {
  now?: Date;
  timeZone?: string;
}

/** An instant as ISO 8601 sends it: a day, `T`, hours and minutes, optional seconds and fraction, optional offset. */
const ISO_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$/;

type MomentStyle = 'time' | 'date-time' | 'year-date-time' | 'date' | 'year-date' | 'whole-date' | 'day-key';

const MOMENT_STYLES: Record<MomentStyle, Intl.DateTimeFormatOptions> = {
  time: { timeStyle: 'short' },
  'date-time': { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' },
  'year-date-time': { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' },
  date: { day: 'numeric', month: 'short' },
  'year-date': { day: 'numeric', month: 'short', year: 'numeric' },
  'whole-date': { dateStyle: 'medium' },
  'day-key': { year: 'numeric', month: 'numeric', day: 'numeric' },
};

const momentFormats = new Map<string, Intl.DateTimeFormat>();

function momentFormat(locale: string, style: MomentStyle, timeZone: string): Intl.DateTimeFormat {
  const id = `${locale}|${style}|${timeZone}`;
  let found = momentFormats.get(id);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { ...MOMENT_STYLES[style], timeZone });
    momentFormats.set(id, found);
  }
  return found;
}

/** The civil day an instant falls on in `timeZone`, as that day's UTC midnight (what `isoDay` gives). */
function dayIn(instant: Date, timeZone: string): Date {
  const parts = momentFormat('en', 'day-key', timeZone).formatToParts(instant);
  const part = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((found) => found.type === type)?.value);
  return new Date(Date.UTC(part('year'), part('month') - 1, part('day')));
}

/** «Today» / «hoy», «Yesterday» / «ayer»: the language's own word, capitalised to open the line. */
function relativeDay(offset: 0 | -1, locale: string): string {
  const word = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(offset, 'day');
  return word.charAt(0).toLocaleUpperCase(locale) + word.slice(1);
}

/** When something happened, as a day's list says it (Square, Shopify, a phone's call log): the local time alone if it
 *  was today («4:23»), «Ayer 18:10» if yesterday, else the short date and the time («20 oct, 18:10»; the year only
 *  when it is another); `detail` says it whole («23 oct 2026, 4:23»). A civil day `YYYY-MM-DD` says «Hoy», «Ayer» or
 *  its date, in no zone. Not a date: `undefined`. */
export function formatMoment(value: string, locale: string, options: MomentOptions = {}): { text: string; detail: string } | undefined {
  const timeZone = options.timeZone ?? new Intl.DateTimeFormat().resolvedOptions().timeZone;
  const now = options.now ?? new Date();
  const civil = isoDay(value);
  const instant = civil || !ISO_INSTANT.test(value) ? undefined : new Date(value);
  if (instant && Number.isNaN(instant.getTime())) return undefined;
  const day = civil ?? (instant ? dayIn(instant, timeZone) : undefined);
  if (!day) return undefined;
  const today = dayIn(now, timeZone);
  const back = Math.round((today.getTime() - day.getTime()) / DAY_MS);
  const sameYear = day.getUTCFullYear() === today.getUTCFullYear();
  if (!instant) {
    const detail = momentFormat(locale, 'whole-date', 'UTC').format(day);
    if (back === 0 || back === 1) return { text: relativeDay(back === 0 ? 0 : -1, locale), detail };
    return { text: momentFormat(locale, sameYear ? 'date' : 'year-date', 'UTC').format(day), detail };
  }
  const detail = formatDateTime(instant, locale, { timeZone });
  const time = () => momentFormat(locale, 'time', timeZone).format(instant);
  if (back === 0) return { text: time(), detail };
  if (back === 1) return { text: `${relativeDay(-1, locale)} ${time()}`, detail };
  return { text: momentFormat(locale, sameYear ? 'date-time' : 'year-date-time', timeZone).format(instant), detail };
}

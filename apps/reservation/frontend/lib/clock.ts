// The book's clock is the business's, never the device's. A reservation keeps its day (`YYYY-MM-DD`) and its
// wall-clock time (`21:00:00`), as said on the phone: both are read as text and painted in UTC arithmetic,
// so no zone of the device can shift them. «Today» and «now» are asked of the business's zone (the
// settings bring it). Pages never format by hand: they call these.

const formats = new Map<string, Intl.DateTimeFormat>();

function formatIn(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale}|${JSON.stringify(options)}`;
  let found = formats.get(key);
  if (!found) {
    try {
      found = new Intl.DateTimeFormat(locale, { ...options, timeZone: 'UTC' });
    } catch {
      found = new Intl.DateTimeFormat('en', { ...options, timeZone: 'UTC' });
    }
    formats.set(key, found);
  }
  return found;
}

const asUtc = (day: string, time = '00:00'): Date => new Date(`${day}T${time}:00Z`);
const iso = (date: Date): string => date.toISOString().slice(0, 10);

/** Today in the business's zone (`2026-10-15`). */
export function todayIn(zone: string, now: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
  } catch {
    return iso(now);
  }
}

/** The business's wall clock now (`2026-10-15T21:05`): what a reservation's day and time compare with. */
export function wallNowIn(zone: string, now: Date = new Date()): string {
  try {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat('en-CA', {
        timeZone: zone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      })
        .formatToParts(now)
        .map((part) => [part.type, part.value]),
    );
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  } catch {
    return now.toISOString().slice(0, 16);
  }
}

/** `day` moved `count` days on the calendar. */
export function addDays(day: string, count: number): string {
  const date = asUtc(day);
  date.setUTCDate(date.getUTCDate() + count);
  return iso(date);
}

/** 0 = Monday … 6 = Sunday, as the slots count the week. */
export function weekdayOf(day: string): number {
  return (asUtc(day).getUTCDay() + 6) % 7;
}

/** A server time (`21:00:00`) as hours and minutes (`21:00`). */
export function hhmm(time: string): string {
  return time.slice(0, 5);
}

/** «Thursday, October 15» / «Jueves, 15 de octubre»: the day bar, sentence case. */
export function formatDay(day: string, locale: string): string {
  const text = formatIn(locale, { weekday: 'long', month: 'long', day: 'numeric' }).format(asUtc(day));
  return text.charAt(0).toLocaleUpperCase(locale) + text.slice(1);
}

/** «10/15/2026» / «15/10/2026»: a date in a table. */
export function formatShortDate(day: string, locale: string): string {
  return formatIn(locale, { year: 'numeric', month: '2-digit', day: '2-digit' }).format(asUtc(day));
}

/** A wall-clock time as the reader writes it («21:00», «9:00 PM»). */
export function formatTime(time: string, locale: string): string {
  if (!time) return '';
  return formatIn(locale, { hour: 'numeric', minute: '2-digit' }).format(asUtc('2000-01-01', hhmm(time)));
}

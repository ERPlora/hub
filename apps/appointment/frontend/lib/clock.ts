// The agenda's clock is the business's, never the device's. The server sends every time on the
// business's clock with its offset (`2026-10-19T10:00:00+02:00`): its first sixteen characters ARE the
// business's wall clock, so they are read as text, never through the device's `Date`. Days are
// `YYYY-MM-DD` and step on the calendar (in UTC arithmetic: no daylight-saving change in between).
// What a person types goes back as wall clock without offset (`2026-10-19T10:00`): the server reads it on
// the business's clock. Pages never format by hand: they call these.

const days = new Map<string, Intl.DateTimeFormat>();

function formatIn(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale}|${JSON.stringify(options)}`;
  let found = days.get(key);
  if (!found) {
    try {
      found = new Intl.DateTimeFormat(locale, { ...options, timeZone: 'UTC' });
    } catch {
      found = new Intl.DateTimeFormat('en', { ...options, timeZone: 'UTC' });
    }
    days.set(key, found);
  }
  return found;
}

const asUtc = (day: string, time = '00:00'): Date => new Date(`${day}T${time}:00Z`);
const iso = (date: Date): string => date.toISOString().slice(0, 10);
const pad = (n: number): string => String(n).padStart(2, '0');

/** The business day of a server time (`2026-10-19`). */
export function dayOf(moment: string): string {
  return moment.slice(0, 10);
}

/** The business's wall-clock time of a server time (`09:05`). */
export function timeOf(moment: string): string {
  return moment.slice(11, 16);
}

/** Minutes from the business's midnight of a server time. */
export function minutesOf(moment: string): number {
  const [hours, minutes] = timeOf(moment).split(':').map(Number);
  return hours * 60 + minutes;
}

/** Today in the business's zone. */
export function todayIn(zone: string, now: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
  } catch {
    return iso(now);
  }
}

/** The business's wall clock now (`2026-10-19T01:30`): what a typed time is compared with. */
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

export function addDays(day: string, count: number): string {
  const date = asUtc(day);
  date.setUTCDate(date.getUTCDate() + count);
  return iso(date);
}

/** The Monday of `day`'s week. */
export function weekStart(day: string): string {
  const weekday = (asUtc(day).getUTCDay() + 6) % 7;
  return addDays(day, -weekday);
}

/** Monday to Sunday of `day`'s week. */
export function weekDays(day: string): string[] {
  const first = weekStart(day);
  return Array.from({ length: 7 }, (_, index) => addDays(first, index));
}

/** «Monday, October 19, 2026» / «lunes, 19 de octubre de 2026». */
export function formatDay(day: string, locale: string): string {
  return formatIn(locale, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }).format(asUtc(day));
}

/** «Mon 19» / «lun 19»: a week's column. */
export function formatShortDay(day: string, locale: string): string {
  return formatIn(locale, { weekday: 'short', day: 'numeric' }).format(asUtc(day)).replace(/[.,]/g, '');
}

/** «Oct 19, 2026» / «19 oct 2026»: a date in a table. */
export function formatShortDate(day: string, locale: string): string {
  return formatIn(locale, { dateStyle: 'medium' }).format(asUtc(day));
}

/** A wall-clock `HH:MM` as the reader writes it («9:05», «9:05 PM»). */
export function formatTime(time: string, locale: string): string {
  return formatIn(locale, { hour: 'numeric', minute: '2-digit' }).format(asUtc('2000-01-01', time.slice(0, 5)));
}

/** A day and a typed time as the business's wall clock the server reads (`2026-10-19T09:05`). */
export function wallInput(day: string, time: string): string {
  const [hours = '0', minutes = '0'] = time.split(':');
  return `${day}T${pad(Number(hours))}:${pad(Number(minutes))}`;
}

/** The device is on another zone than the business: the agenda says it paints the business's clock. */
export function deviceZoneDiffers(zone: string): boolean {
  return Intl.DateTimeFormat().resolvedOptions().timeZone !== zone;
}

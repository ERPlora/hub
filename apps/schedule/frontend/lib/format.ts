// How the schedule screens paint a wall-clock time and a calendar day (pages never format by hand). A
// time is the business's wall clock (`HH:MM:SS` on the wire): painted in the clock of the reader's
// language (24 hours in Spanish, AM/PM in English), built and formatted in UTC so the device's zone
// never moves it. A calendar day (`YYYY-MM-DD`) is a day, not an instant: painted in UTC too.
// `@erplora/ui` has `formatDateTime` only; these are asked for in apps/schedule/UI-REQUESTS.md.

const DASH = '—';
const STORED_TIME = /^(\d{2}):(\d{2})(?::\d{2})?$/;

const timeFormats = new Map<string, Intl.DateTimeFormat>();
const dateFormats = new Map<string, Intl.DateTimeFormat>();

function timeFormat(locale: string): Intl.DateTimeFormat {
  let found = timeFormats.get(locale);
  if (!found) {
    const options: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' };
    try {
      found = new Intl.DateTimeFormat(locale, options);
    } catch {
      found = new Intl.DateTimeFormat('en', options);
    }
    timeFormats.set(locale, found);
  }
  return found;
}

function dateFormat(locale: string): Intl.DateTimeFormat {
  let found = dateFormats.get(locale);
  if (!found) {
    const options: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' };
    try {
      found = new Intl.DateTimeFormat(locale, options);
    } catch {
      found = new Intl.DateTimeFormat('en', options);
    }
    dateFormats.set(locale, found);
  }
  return found;
}

/** A wall-clock time in the clock of `locale` («14:30», «02:30 PM»); anything else as it came. */
export function formatTime(value: string, locale: string): string {
  const match = STORED_TIME.exec(value);
  if (!match) return value;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return value;
  return timeFormat(locale).format(new Date(Date.UTC(2026, 0, 1, hour, minute)));
}

/** An interval: «10:00–14:00». */
export function formatSpan(open: string, close: string, locale: string): string {
  return `${formatTime(open, locale)}–${formatTime(close, locale)}`;
}

/** A calendar day (`YYYY-MM-DD`) in the reader's order (`25/12/2026`, `12/25/2026`); none is a dash. */
export function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return DASH;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : dateFormat(locale).format(date);
}

/** What a time field (`type="time"`) holds for a value of the API: `HH:MM`, or `''`. */
export function timeValue(value: string | null | undefined): string {
  return value ? value.slice(0, 5) : '';
}

// How the time clock paints instants, days and durations (pages never format by hand). Every wall-clock
// time and calendar day is the BUSINESS's, never the device's: a manager checking the shop from abroad
// sees the day the employee clocked in. Phase 1 has one zone, the Hub's `TIME_ZONE` (Europe/Madrid);
// the business's own zone arrives with the hub's settings. Durations come from the server in seconds,
// as of its `as_of`, and run on from there with the page's clock.

/** The business's time zone (phase 1: the Hub's `TIME_ZONE`). */
export const BUSINESS_TIME_ZONE = 'Europe/Madrid';

const DASH = '—';

interface Parts {
  year: string;
  month: string;
  day: string;
  hour: string;
  minute: string;
}

const partsFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: BUSINESS_TIME_ZONE,
  hourCycle: 'h23',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

function partsOf(ms: number): Parts {
  const out: Record<string, string> = {};
  for (const part of partsFormat.formatToParts(new Date(ms))) if (part.type !== 'literal') out[part.type] = part.value;
  return { year: out.year, month: out.month, day: out.day, hour: out.hour === '24' ? '00' : out.hour, minute: out.minute };
}

const readable = (iso: string | null | undefined): number | null => {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
};

const whole = (n: number): number => (Number.isFinite(n) && n > 0 ? Math.floor(n) : 0);
const pad2 = (n: number): string => String(n).padStart(2, '0');

/** Business wall-clock `HH:MM` of an instant; `''` when it is missing or unreadable. */
export function formatTime(iso: string | null | undefined): string {
  const ms = readable(iso);
  if (ms === null) return '';
  const p = partsOf(ms);
  return `${p.hour}:${p.minute}`;
}

/** Seconds as `h:mm` (`27120` → `7:32`). */
export function formatHm(seconds: number): string {
  const minutes = Math.floor(whole(seconds) / 60);
  return `${Math.floor(minutes / 60)}:${pad2(minutes % 60)}`;
}

/** Seconds as `h:mm:ss`, the running clock of an open day. */
export function formatHms(seconds: number): string {
  const s = whole(seconds);
  return `${Math.floor(s / 3600)}:${pad2(Math.floor((s % 3600) / 60))}:${pad2(s % 60)}`;
}

/** A server figure (`seconds` as of `asOf`) as it is at `now`: it runs on only while it `grows`. */
export function liveSeconds(seconds: number, asOf: string, now: number, grows: boolean): number {
  if (!grows) return seconds;
  const since = readable(asOf);
  return since === null ? seconds : seconds + whole((now - since) / 1000);
}

/** A business day `YYYY-MM-DD` as a short date («Tue, Oct 6», «mar, 6 oct»), read as a plain date. */
export function formatDay(day: string, locale: string): string {
  const [y, m, d] = day.split('-').map(Number);
  if (!y || !m || !d) return day;
  return new Intl.DateTimeFormat(locale, { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' })
    .format(new Date(Date.UTC(y, m - 1, d)))
    .replace(/\./g, '');
}

/** Business `YYYY-MM-DD` of an instant. */
export function localDate(iso: string): string {
  const p = partsOf(Date.parse(iso));
  return `${p.year}-${p.month}-${p.day}`;
}

/** Business `YYYY-MM-DD HH:MM` of an instant (the history's and the CSV's form). */
export function localDateTime(iso: string | null | undefined): string {
  const ms = readable(iso);
  if (ms === null) return DASH;
  const p = partsOf(ms);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
}

/** `HH:MM`, with the day when it is not the day of the clock-in (a night shift); `—` when missing. */
export function timeOfDay(iso: string | null | undefined, workDate: string, locale: string): string {
  const ms = readable(iso);
  if (ms === null) return DASH;
  const p = partsOf(ms);
  const time = `${p.hour}:${p.minute}`;
  if (`${p.year}-${p.month}-${p.day}` === workDate) return time;
  const day = new Intl.DateTimeFormat(locale, { timeZone: BUSINESS_TIME_ZONE, day: '2-digit', month: '2-digit' }).format(new Date(ms));
  return `${time} (${day})`;
}

/** The value of a `datetime-local` field showing an instant in business time. */
export function toLocalInput(iso: string): string {
  const p = partsOf(Date.parse(iso));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

/** The business month `YYYY-MM` of an instant. */
export function monthOf(ms: number): string {
  const p = partsOf(ms);
  return `${p.year}-${p.month}`;
}

/** `count` months ending at `month`, newest first (49 = this month and the four years the law keeps). */
export function recentMonths(month: string, count: number): string[] {
  const [y, m] = month.split('-').map(Number);
  const out: string[] = [];
  for (let i = 0; i < count; i++) {
    const total = y * 12 + (m - 1) - i;
    out.push(`${Math.floor(total / 12)}-${pad2((total % 12) + 1)}`);
  }
  return out;
}

/** The first and last business days of a month, as the list's date filters take them. */
export function monthBounds(month: string): { date_from: string; date_to: string } {
  const [y, m] = month.split('-').map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return { date_from: `${month}-01`, date_to: `${month}-${pad2(last)}` };
}

/** A month in the reader's language, capitalised («October 2026», «Octubre de 2026»). */
export function monthLabel(month: string, locale: string): string {
  const [y, m] = month.split('-').map(Number);
  const label = new Intl.DateTimeFormat(locale, { timeZone: 'UTC', month: 'long', year: 'numeric' }).format(
    new Date(Date.UTC(y, m - 1, 1)),
  );
  return label.charAt(0).toUpperCase() + label.slice(1);
}

// A day of the card (birthday, anniversary: `YYYY-MM-DD`, or `--MM-DD` when the year is not known, as vCard writes
// it) in the page language, and the day, month and year a person types for it. A day has no time nor zone: it is
// formatted in UTC so it never moves to the day before. Until `@erplora/ui`'s formatters paint days too
// (UI-REQUESTS.md), this is the one place the app does it.

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale} ${JSON.stringify(options)}`;
  let found = formatters.get(key);
  if (!found) {
    try {
      found = new Intl.DateTimeFormat(locale, { ...options, timeZone: 'UTC' });
    } catch {
      found = new Intl.DateTimeFormat('en', { ...options, timeZone: 'UTC' });
    }
    formatters.set(key, found);
  }
  return found;
}

const DAY = /^(\d{4}|-)-(\d{2})-(\d{2})$/;
/** A leap year, so a day without its year may be the 29th of February. */
const ANY_YEAR = 2000;

/** `YYYY-MM-DD` in `locale` («Feb 3, 1990», «3 feb 1990»), `--MM-DD` by its day and month («12 de marzo»); nothing is «—». */
export function formatDay(value: string | null | undefined, locale: string): string {
  if (!value) return '—';
  const match = DAY.exec(value);
  if (!match) return value;
  const [, year, month, day] = match;
  const yearless = year === '-';
  const options: Intl.DateTimeFormatOptions = yearless ? { day: 'numeric', month: 'long' } : { dateStyle: 'medium' };
  return formatter(locale, options).format(Date.UTC(yearless ? ANY_YEAR : Number(year), Number(month) - 1, Number(day)));
}

/** What a person types for a birthday or an anniversary: the year may stay empty. */
export interface AnnualDateParts {
  day: string;
  month: string;
  year: string;
}

export type AnnualDatePart = keyof AnnualDateParts;

const twoDigits = (part: string): string => (/^\d$/.test(part) ? `0${part}` : part);

/** The day the card keeps for `parts`: `--MM-DD` without the year, `YYYY-MM-DD` with it, `''` with nothing typed. A
 *  part missing or that is no number goes up as typed: the server refuses it under its field, as any wrong day. */
export function annualDate(parts: AnnualDateParts): string {
  const [day, month, year] = [parts.day.trim(), parts.month.trim(), parts.year.trim()];
  if (!day && !month && !year) return '';
  return `${year || '-'}-${twoDigits(month)}-${twoDigits(day)}`;
}

/** The parts of a day the card keeps; anything else, none. */
export function annualDateParts(value: string | null | undefined): AnnualDateParts {
  const match = DAY.exec(value ?? '');
  if (!match) return { day: '', month: '', year: '' };
  return { day: String(Number(match[3])), month: String(Number(match[2])), year: match[1] === '-' ? '' : match[1] };
}

/** The parts in the order `locale` writes a day: «14/3/1990» in Spanish, «3/14/1990» in English. */
export function annualDateOrder(locale: string): AnnualDatePart[] {
  const parts = formatter(locale, { day: 'numeric', month: 'numeric', year: 'numeric' }).formatToParts(0);
  return parts.map((part) => part.type).filter((type): type is AnnualDatePart => type === 'day' || type === 'month' || type === 'year');
}

// A day of the card (birthday, anniversary: `YYYY-MM-DD`) in the page language. A day has no time
// nor zone: it is formatted in UTC so it never moves to the day before. Until `@erplora/ui`'s
// formatters paint days too (UI-REQUESTS.md), this is the one place the app does it.

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(locale: string): Intl.DateTimeFormat {
  let found = formatters.get(locale);
  if (!found) {
    try {
      found = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' });
    } catch {
      found = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeZone: 'UTC' });
    }
    formatters.set(locale, found);
  }
  return found;
}

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** `YYYY-MM-DD` in `locale` («Feb 3, 1990», «3 feb 1990»); nothing is «—». */
export function formatDay(value: string | null | undefined, locale: string): string {
  if (!value) return '—';
  const match = DAY.exec(value);
  if (!match) return value;
  const [, year, month, day] = match.map(Number);
  return formatter(locale).format(Date.UTC(year, month - 1, day));
}

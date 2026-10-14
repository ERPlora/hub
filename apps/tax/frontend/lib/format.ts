// How the tax screens show a rate and a day in the reader's language. `@erplora/ui` has a date-and-time
// formatter only (`formatDateTime`); these two are asked for in apps/tax/UI-REQUESTS.md and move there
// when it has them. Pages never format by hand: they call these.

const percents = new Map<string, Intl.NumberFormat>();
const dates = new Map<string, Intl.DateTimeFormat>();

function percentIn(locale: string): Intl.NumberFormat {
  let found = percents.get(locale);
  if (!found) {
    const options: Intl.NumberFormatOptions = { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 };
    try {
      found = new Intl.NumberFormat(locale, options);
    } catch {
      found = new Intl.NumberFormat('en', options);
    }
    percents.set(locale, found);
  }
  return found;
}

function dateIn(locale: string): Intl.DateTimeFormat {
  let found = dates.get(locale);
  if (!found) {
    // UTC: a rule's day is a calendar date, never shifted by the device's time zone.
    const options: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeZone: 'UTC' };
    try {
      found = new Intl.DateTimeFormat(locale, options);
    } catch {
      found = new Intl.DateTimeFormat('en', options);
    }
    dates.set(locale, found);
  }
  return found;
}

/** A tax rate in % (the server's decimal string) as the reader writes it: «21,00 %», «21.00%». */
export function formatPercent(rate: string | number, locale: string): string {
  const value = Number(rate);
  if (typeof rate === 'string' && (rate.trim() === '' || !Number.isFinite(value))) return rate;
  return percentIn(locale).format(value / 100);
}

/** A calendar day (`YYYY-MM-DD`) in the reader's language; empty for none, as it came if not a date. */
export function formatDate(day: string | null | undefined, locale: string): string {
  if (!day) return '';
  const date = /^\d{4}-\d{2}-\d{2}$/.test(day) ? new Date(`${day}T00:00:00Z`) : new Date(Number.NaN);
  return Number.isNaN(date.getTime()) ? day : dateIn(locale).format(date);
}

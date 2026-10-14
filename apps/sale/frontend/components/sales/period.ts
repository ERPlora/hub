// The period of the Sales screen (SALE-F28): «Today» (to begin with), «7 days», «30 days» or «All»,
// counted back from the business day with both ends included. The server filters rows and figures by
// business day (`date_from`, `date_to`); the arithmetic is on calendar days in UTC, so a DST change
// never slips a day.

export const PERIODS = ['today', 'week', 'month', 'all'] as const;
export type Period = (typeof PERIODS)[number];

/** Business days, ISO, both included; absent = unbounded. */
export interface DayBounds {
  date_from?: string;
  date_to?: string;
}

const DAYS_BACK: Record<Exclude<Period, 'all'>, number> = { today: 0, week: 6, month: 29 };

/** The days `period` covers, ending on `today` (an ISO day). */
export function periodBounds(period: Period, today: string): DayBounds {
  if (period === 'all') return {};
  const [year, month, day] = today.split('-').map(Number);
  const from = new Date(Date.UTC(year, month - 1, day - DAYS_BACK[period])).toISOString().slice(0, 10);
  return { date_from: from, date_to: today };
}

const pad = (n: number): string => String(n).padStart(2, '0');

/** The device's local calendar day, as an ISO day. */
export function deviceDay(now: Date = new Date()): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

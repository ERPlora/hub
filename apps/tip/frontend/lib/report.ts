// What the report of the team's tips says of each line, and the CSV «Export» saves: the lines as on screen, amounts as
// plain numbers in the business's money so a spreadsheet can add them up.
import { formatDateTime, type Money } from '@erplora/ui/components';

import type { ReportBy, ReportOut, ReportRowOut } from '../operations';

type Translate = (key: string) => string;

export interface ReportSay {
  t: Translate;
  locale: string;
  /** The business's time zone; the device's while unknown. */
  zone?: string;
  money: Money;
}

const AMOUNTS = ['card', 'cash', 'other', 'total'] as const;
/** What a spreadsheet runs as a formula when a cell starts with it (OWASP «CSV injection»). */
const FORMULA_STARTS = ['=', '+', '-', '@', '\t', '\r'];

/** Whose the line is; nobody's is unassigned by person, and outside every clocked working day by shift. */
export function lineName(row: ReportRowOut, by: ReportBy, t: Translate): string {
  if (row.member_name) return row.member_name;
  return by === 'person' ? t('tip.list.unassigned') : t('tip.report.outside');
}

/** The working day of a line by shift, on the business's clock: from its clock-in to its clock-out, or still open. */
export function shiftText(row: ReportRowOut, say: Omit<ReportSay, 'money'>): string {
  if (!row.clock_in_at) return '—';
  const start = formatDateTime(row.clock_in_at, say.locale, { timeZone: say.zone });
  const end = row.clock_out_at
    ? new Intl.DateTimeFormat(say.locale, { timeStyle: 'short', timeZone: say.zone }).format(new Date(row.clock_out_at))
    : say.t('tip.report.open');
  return `${start} – ${end}`;
}

function plain(cents: number, money: Money): string {
  return (cents / 10 ** money.decimals).toFixed(money.decimals);
}

function cell(text: string): string {
  const safe = FORMULA_STARTS.some((start) => text.startsWith(start)) ? `'${text}` : text;
  return /[",\r\n]/.test(safe) || safe !== text ? `"${safe.replaceAll('"', '""')}"` : safe;
}

/** The report as CSV, a line per row of the screen under its column names. */
export function reportCsv(report: ReportOut, say: ReportSay): string {
  const byShift = report.by === 'shift';
  const header = ['person', ...(byShift ? ['shift'] : []), 'count', ...AMOUNTS].map((column) => say.t(`tip.report.columns.${column}`));
  const lines = report.rows.map((row) => [
    cell(lineName(row, report.by, say.t)),
    ...(byShift ? [cell(shiftText(row, say))] : []),
    String(row.count),
    ...AMOUNTS.map((amount) => plain(row[amount], say.money)),
  ]);
  return [header.map(cell), ...lines].map((line) => `${line.join(',')}\r\n`).join('');
}

/** `tips-by-person-2026-11-19_2026-11-25.csv`; a single day once. */
export function reportFilename(report: ReportOut): string {
  const days = report.date_from === report.date_to ? report.date_from : `${report.date_from}_${report.date_to}`;
  return `tips-by-${report.by}-${days}.csv`;
}

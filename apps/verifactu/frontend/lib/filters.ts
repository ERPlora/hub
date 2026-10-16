// The filters of the VeriFactu lists (Records: status, type, invoice type, environment, issue days and total;
// Events: type, severity and days), as the table's funnel holds them (by name, as typed; a filter not in use is
// absent) and as the list queries take them: the closed lists and the days as they are, the totals in cents.
// A total it cannot read, or a day «until» before its «from», does not filter: the table says it under it.
import type { DataTableFilters } from '@erplora/ui/components';

import { centsFromEuros } from './format';

const AMOUNTS = ['total_amount_from', 'total_amount_to'];
/** The ranges of days, [from, until]. */
const DAYS = [
  ['issue_date_from', 'issue_date_to'],
  ['date_from', 'date_to'],
] as const;

/** The totals typed that are not amounts. */
export function unreadableAmounts(values: DataTableFilters): string[] {
  return AMOUNTS.filter((name) => values[name] && centsFromEuros(values[name]) === undefined);
}

/** The days «until» before their «from» (`YYYY-MM-DD`, so they compare as text). */
export function backwardsDays(values: DataTableFilters): string[] {
  return DAYS.filter(([from, until]) => values[from] && values[until] && values[until] < values[from]).map(([, until]) => until);
}

/** What the list query takes: the text as it is, the totals in cents (what it cannot take is left out). */
export function filterParams(values: DataTableFilters): Record<string, string | number> {
  const backwards = backwardsDays(values);
  const out: Record<string, string | number> = {};
  for (const [name, value] of Object.entries(values)) {
    if (!value || backwards.includes(name)) continue;
    if (AMOUNTS.includes(name)) {
      const cents = centsFromEuros(value);
      if (cents !== undefined) out[name] = cents;
    } else out[name] = value;
  }
  return out;
}

/** The filters that really apply. */
export function filtersInUse(values: DataTableFilters): number {
  return Object.keys(filterParams(values)).length;
}

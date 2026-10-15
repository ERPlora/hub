// The filters of the VeriFactu lists as the panel keeps them (the text typed) and as the list queries take them
// (totals in cents). An amount that is not one never reaches the server: the panel marks it.
import { centsFromEuros } from '../lib/format';

export type FilterValues = Partial<Record<string, string>>;

const AMOUNTS = ['total_amount_from', 'total_amount_to'];
const RANGES = [
  ['issue_date_from', 'issue_date_to'],
  ['total_amount_from', 'total_amount_to'],
  ['date_from', 'date_to'],
];

/** Filters in use; a range (from–until) counts once. */
export function filterCount(values: FilterValues): number {
  const used = Object.keys(values).filter((key) => values[key]);
  const ranged = RANGES.filter((pair) => pair.some((key) => used.includes(key))).length;
  return used.filter((key) => !RANGES.flat().includes(key)).length + ranged;
}

/** The amounts typed that are not amounts. */
export function invalidAmounts(values: FilterValues): string[] {
  return AMOUNTS.filter((key) => values[key] && centsFromEuros(values[key]) === undefined);
}

/** What the list query takes: the text as it is, the totals in cents (a wrong amount is left out). */
export function filterQuery(values: FilterValues): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(values)) {
    if (!value) continue;
    if (AMOUNTS.includes(key)) {
      const cents = centsFromEuros(value);
      if (cents !== undefined) out[key] = cents;
    } else out[key] = value;
  }
  return out;
}

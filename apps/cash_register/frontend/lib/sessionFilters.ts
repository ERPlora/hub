// The filters of the sessions list (CASH_REGISTER Pantallas · Caja: status, number and the four amounts),
// as the table's funnel holds them (by name, as typed, in the business's money; a filter not in use is
// absent) and as `cash_register.session.list` takes them (cents), read as every amount filter of the Hub
// (`filterCents`, hub#1196). Only the difference takes a minus (a short drawer). An amount it cannot read does not
// filter: the table says it under its field (the page, with `amountFilterErrors` on `AMOUNT_FILTERS`, `SIGNED`).
import type { DataTableFilters } from '@erplora/ui/components';

import type { SessionListIn, SessionStatus } from '../operations';
import { filterCents, type Money } from './money';

export const SESSION_STATUSES: readonly SessionStatus[] = ['open', 'closed'];

/** The four amounts, each from–to, by the names the list query takes. */
export const AMOUNT_RANGES = {
  opening: ['opening_min', 'opening_max'],
  expected: ['expected_min', 'expected_max'],
  counted: ['counted_min', 'counted_max'],
  difference: ['difference_min', 'difference_max'],
} as const;

type AmountFilter = (typeof AMOUNT_RANGES)[keyof typeof AMOUNT_RANGES][number];

/** The eight amount ends, in the business's money as typed. */
export const AMOUNT_FILTERS: readonly AmountFilter[] = Object.values(AMOUNT_RANGES).flat();
/** The ends that take a minus: the difference's (a short drawer). */
export const SIGNED: readonly AmountFilter[] = AMOUNT_RANGES.difference;

const filled = (text: string | undefined): text is string => (text ?? '').trim() !== '';

/** The filters as `cash_register.session.list` takes them. */
export function filterParams(values: DataTableFilters, money?: Money): Partial<SessionListIn> {
  const out: Partial<SessionListIn> = {};
  if (SESSION_STATUSES.includes(values.status as SessionStatus)) out.status = values.status as SessionStatus;
  if (filled(values.number)) out.number = values.number.trim();
  for (const name of AMOUNT_FILTERS) {
    const text = values[name];
    if (!filled(text)) continue;
    const amount = filterCents(text, money, { signed: SIGNED.includes(name) });
    if (amount !== undefined) out[name] = amount;
  }
  return out;
}

/** The filters that really apply (an amount it cannot read does not). */
export function filtersInUse(values: DataTableFilters, money?: Money): number {
  return Object.keys(filterParams(values, money)).length;
}

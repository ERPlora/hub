// The filters of the sessions list (CASH_REGISTER Pantallas · Caja: status, number and the four amounts),
// as the table's funnel holds them (by name, as typed, in the business's money; a filter not in use is
// absent) and as `cash_register.session.list` takes them (cents). Only the difference takes a minus (a
// short drawer). An amount it cannot read does not filter: the table says it under its field.
import type { DataTableFilters } from '@erplora/ui/components';

import type { SessionListIn, SessionStatus } from '../operations';
import { type Money, moneyDecimals, readMoney } from './money';

export const SESSION_STATUSES: readonly SessionStatus[] = ['open', 'closed'];

/** The four amounts, each from–to, by the names the list query takes. */
export const AMOUNT_RANGES = {
  opening: ['opening_min', 'opening_max'],
  expected: ['expected_min', 'expected_max'],
  counted: ['counted_min', 'counted_max'],
  difference: ['difference_min', 'difference_max'],
} as const;

type AmountFilter = (typeof AMOUNT_RANGES)[keyof typeof AMOUNT_RANGES][number];

const AMOUNT_FILTERS: readonly AmountFilter[] = Object.values(AMOUNT_RANGES).flat();

const filled = (text: string | undefined): text is string => (text ?? '').trim() !== '';

/** An amount filter as cents of the business's `money`; `undefined` when it is no amount (a minus only for the
 *  difference). */
function cents(name: AmountFilter, text: string, money?: Money): number | undefined {
  const trimmed = text.trim();
  const negative = name.startsWith('difference') && /^[-−]/.test(trimmed);
  const read = readMoney(negative ? trimmed.slice(1) : trimmed, moneyDecimals(money), money?.currency);
  if (!read.ok || read.cents === null) return undefined;
  return negative ? -read.cents : read.cents;
}

/** The amounts typed that are not amounts: the table says it under each. */
export function unreadableAmounts(values: DataTableFilters, money?: Money): string[] {
  return AMOUNT_FILTERS.filter((name) => filled(values[name]) && cents(name, values[name], money) === undefined);
}

/** The filters as `cash_register.session.list` takes them. */
export function filterParams(values: DataTableFilters, money?: Money): Partial<SessionListIn> {
  const out: Partial<SessionListIn> = {};
  if (SESSION_STATUSES.includes(values.status as SessionStatus)) out.status = values.status as SessionStatus;
  if (filled(values.number)) out.number = values.number.trim();
  for (const name of AMOUNT_FILTERS) {
    const text = values[name];
    if (!filled(text)) continue;
    const amount = cents(name, text, money);
    if (amount !== undefined) out[name] = amount;
  }
  return out;
}

/** The filters that really apply (an amount it cannot read does not). */
export function filtersInUse(values: DataTableFilters, money?: Money): number {
  return Object.keys(filterParams(values, money)).length;
}

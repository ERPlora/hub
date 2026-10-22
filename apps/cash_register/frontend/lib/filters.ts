// The filters of the sessions list (CASH_REGISTER Pantallas · Caja: status, number and the four amounts),
// as the panel keeps them (the text typed, in the business's money) and as `cash_register.session.list`
// takes them (cents). Only the difference takes a minus (a short drawer). An amount that is not one never
// reaches the server: the panel marks it.
import type { SessionListIn, SessionStatus } from '../operations';
import { readMoney } from './money';

export const SESSION_STATUSES: readonly SessionStatus[] = ['open', 'closed'];

export const AMOUNT_FILTERS = [
  'opening_min',
  'opening_max',
  'expected_min',
  'expected_max',
  'counted_min',
  'counted_max',
  'difference_min',
  'difference_max',
] as const;

export type SessionFilterKey = 'status' | 'number' | (typeof AMOUNT_FILTERS)[number];
/** Filter values as typed; a filter not in use is absent. */
export type SessionFilterValues = Readonly<Partial<Record<SessionFilterKey, string>>>;

const filled = (values: SessionFilterValues, key: SessionFilterKey): boolean => (values[key] ?? '').trim() !== '';

/** An amount filter as cents; `undefined` when it is no amount (a minus only for the difference). */
function cents(key: SessionFilterKey, text: string): number | undefined {
  const trimmed = text.trim();
  const negative = key.startsWith('difference') && /^[-−]/.test(trimmed);
  const read = readMoney(negative ? trimmed.slice(1) : trimmed);
  if (!read.ok || read.cents === null) return undefined;
  return negative ? -read.cents : read.cents;
}

/** The amount filters typed that are not amounts. */
export function invalidAmounts(values: SessionFilterValues): SessionFilterKey[] {
  return AMOUNT_FILTERS.filter((key) => filled(values, key) && cents(key, values[key]!) === undefined);
}

/** Filters in use; a range counts once. */
export function filterCount(values: SessionFilterValues): number {
  const ranges = ['opening', 'expected', 'counted', 'difference'].map(
    (name) => filled(values, `${name}_min` as SessionFilterKey) || filled(values, `${name}_max` as SessionFilterKey),
  );
  return [filled(values, 'status'), filled(values, 'number'), ...ranges].filter(Boolean).length;
}

/** What the list query takes from the filters. */
export function filterQuery(values: SessionFilterValues): Partial<SessionListIn> {
  const query: Partial<SessionListIn> = {};
  if (SESSION_STATUSES.includes(values.status as SessionStatus)) query.status = values.status as SessionStatus;
  if (filled(values, 'number')) query.number = values.number!.trim();
  for (const key of AMOUNT_FILTERS) {
    if (!filled(values, key)) continue;
    const amount = cents(key, values[key]!);
    if (amount !== undefined) query[key] = amount;
  }
  return query;
}

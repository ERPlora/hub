// The filters of the customer list (CUSTOMER-F02), as the table's funnel holds them (by name, as
// typed; a filter not in use is absent) and as `customer.customer.list` takes them: a yes/no for
// active, cents for spent. «Spent» is typed in euros; an amount it cannot read does not filter.
import type { DataTableFilters } from '@erplora/ui/components';

import type { CustomerFilters, CustomerSource, CustomerStage } from '../operations';
import { centsFromEuros, readEuros } from './money';

/** Every source a card can have (an imported card says so): the «Source» filter's choices. */
export const SOURCES: readonly CustomerSource[] = ['walk_in', 'phone', 'whatsapp', 'website', 'social', 'referral', 'import', 'other'];

/** The two ends of «Spent», in euros as typed. */
const SPENT_ENDS = ['spent_from', 'spent_to'] as const;

/** The ends of «Spent» typed that are not an amount: the table says it under each. */
export function unreadableAmounts(values: DataTableFilters): string[] {
  return SPENT_ENDS.filter((name) => readEuros(values[name]).kind === 'invalid');
}

/** The filters as `customer.customer.list` takes them. */
export function filterParams(values: DataTableFilters): Partial<CustomerFilters> {
  const out: Partial<CustomerFilters> = {};
  if (values.lifecycle_stage) out.lifecycle_stage = values.lifecycle_stage as CustomerStage;
  if (values.source) out.source = values.source as CustomerSource;
  if (values.is_active) out.is_active = values.is_active === 'true';
  const min = centsFromEuros(values.spent_from);
  const max = centsFromEuros(values.spent_to);
  if (min !== undefined) out.spent_min = min;
  if (max !== undefined) out.spent_max = max;
  return out;
}

/** The filters that really apply (an amount it cannot read does not). */
export function filtersInUse(values: DataTableFilters): number {
  return Object.keys(filterParams(values)).length;
}

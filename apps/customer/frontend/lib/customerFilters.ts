// The filters of the customer list (CUSTOMER-F02), as the table's funnel holds them (by name, as
// typed; a filter not in use is absent) and as `customer.customer.list` takes them: a yes/no for
// active, minor units for spent. «Spent» is typed in the business's `money` (customer-business-currency); an
// amount it cannot read does not filter.
import type { DataTableFilters } from '@erplora/ui/components';

import type { CustomerFilters, CustomerSource, CustomerStage } from '../operations';
import { centsFromAmount, type Money, readAmount } from './money';

/** Every source a card can have (an imported card says so): the «Source» filter's choices. */
export const SOURCES: readonly CustomerSource[] = ['walk_in', 'phone', 'whatsapp', 'website', 'social', 'referral', 'import', 'other'];

/** The two ends of «Spent», in the business's money as typed. */
const SPENT_ENDS = ['spent_from', 'spent_to'] as const;

/** The ends of «Spent» typed that are not an amount of `money`: the table says it under each. */
export function unreadableAmounts(values: DataTableFilters, money?: Money): string[] {
  return SPENT_ENDS.filter((name) => readAmount(values[name], money).kind === 'invalid');
}

/** The filters as `customer.customer.list` takes them, «Spent» in minor units of `money`. */
export function filterParams(values: DataTableFilters, money?: Money): Partial<CustomerFilters> {
  const out: Partial<CustomerFilters> = {};
  if (values.lifecycle_stage) out.lifecycle_stage = values.lifecycle_stage as CustomerStage;
  if (values.source) out.source = values.source as CustomerSource;
  if (values.is_active) out.is_active = values.is_active === 'true';
  const min = centsFromAmount(values.spent_from, money);
  const max = centsFromAmount(values.spent_to, money);
  if (min !== undefined) out.spent_min = min;
  if (max !== undefined) out.spent_max = max;
  return out;
}

/** The filters that really apply (an amount it cannot read does not). */
export function filtersInUse(values: DataTableFilters, money?: Money): number {
  return Object.keys(filterParams(values, money)).length;
}

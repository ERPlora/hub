// The filters of Products (WORKBOOK «Productos»: name, SKU, price from/to, stock from/to and status), as
// the table's funnel holds them (by the list's parameter names, as typed; a filter not in use is absent)
// and as `inventory.product.list` takes them: the price in cents (typed in the business's money, inventory#115, read as
// every amount filter of the Hub: `filterCents`, hub#1196) and the stock as an exact quantity. An end it cannot read
// does not filter: the table says why under it (the page, with `amountFilterErrors` on `PRICE_ENDS` and
// `unreadableQuantities`).
import type { DataTableFilters } from '@erplora/ui/components';
import type { InputOf } from '@erplora/ui/sdk';

import { filterCents, type Money } from './format';
import { readQuantity } from './quantity';

type ProductListIn = InputOf<'inventory.product.list'>;
export type ProductStatus = NonNullable<ProductListIn['status']>;

/** The «Status» filter's choices, in order: «Yes», «No», «Not configured», «Sold out» (INVENTORY-F29). */
export const PRODUCT_STATUSES: readonly ProductStatus[] = ['active', 'inactive', 'needs_tax_setup', 'sold_out'];

/** The two ends of «Price», in the business's money as typed. */
export const PRICE_ENDS = ['price_min', 'price_max'] as const;
const QUANTITY_ENDS = ['stock_min', 'stock_max'] as const;

/** The ends of «Stock» typed that are no quantity, in the panel's order. */
export function unreadableQuantities(values: DataTableFilters): string[] {
  return QUANTITY_ENDS.filter((name) => !readQuantity(values[name] ?? '').ok);
}

/** The filters as `inventory.product.list` (and its export) takes them. */
export function filterParams(values: DataTableFilters, money?: Money): Partial<ProductListIn> {
  const out: Partial<ProductListIn> = {};
  const name = values.name?.trim();
  const sku = values.sku?.trim();
  if (name) out.name = name;
  if (sku) out.sku = sku;
  for (const end of PRICE_ENDS) {
    const cents = filterCents(values[end], money);
    if (cents !== undefined) out[end] = cents;
  }
  for (const end of QUANTITY_ENDS) {
    const read = readQuantity(values[end] ?? '');
    if (read.ok && read.value !== null) out[end] = read.value;
  }
  if (PRODUCT_STATUSES.includes(values.status as ProductStatus)) out.status = values.status as ProductStatus;
  return out;
}

/** The filters that really apply (an end it cannot read does not). */
export function filtersInUse(values: DataTableFilters, money?: Money): number {
  return Object.keys(filterParams(values, money)).length;
}

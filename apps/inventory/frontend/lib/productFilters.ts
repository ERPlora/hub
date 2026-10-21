// The filters of Products (WORKBOOK «Productos»: name, SKU, price from/to, stock from/to and status), as
// the table's funnel holds them (by the list's parameter names, as typed; a filter not in use is absent)
// and as `inventory.product.list` takes them: the price in cents (typed in euros, inventory#115) and the
// stock as an exact quantity. An end it cannot read does not filter: the table says why under it.
import type { DataTableFilters } from '@erplora/ui/components';
import type { InputOf } from '@erplora/ui/sdk';

import { type MoneyRead, parseMoney } from './money';
import { readQuantity } from './quantity';

type ProductListIn = InputOf<'inventory.product.list'>;
export type ProductStatus = NonNullable<ProductListIn['status']>;

/** The «Status» filter's choices, in order: «Yes», «No», «Not configured», «Sold out» (INVENTORY-F29). */
export const PRODUCT_STATUSES: readonly ProductStatus[] = ['active', 'inactive', 'needs_tax_setup', 'sold_out'];

const MONEY_ENDS = ['price_min', 'price_max'] as const;
const QUANTITY_ENDS = ['stock_min', 'stock_max'] as const;

/** An end typed that cannot be read: an amount (with why) or a quantity. */
export interface UnreadableEnd {
  name: string;
  problem: Exclude<MoneyRead, { ok: true }> | 'not_quantity';
}

/** The ends typed that cannot be read, in the panel's order. */
export function unreadableEnds(values: DataTableFilters): UnreadableEnd[] {
  const out: UnreadableEnd[] = [];
  for (const name of MONEY_ENDS) {
    const read = parseMoney(values[name] ?? '');
    if (!read.ok) out.push({ name, problem: read });
  }
  for (const name of QUANTITY_ENDS) if (!readQuantity(values[name] ?? '').ok) out.push({ name, problem: 'not_quantity' });
  return out;
}

/** The filters as `inventory.product.list` (and its export) takes them. */
export function filterParams(values: DataTableFilters): Partial<ProductListIn> {
  const out: Partial<ProductListIn> = {};
  const name = values.name?.trim();
  const sku = values.sku?.trim();
  if (name) out.name = name;
  if (sku) out.sku = sku;
  for (const end of MONEY_ENDS) {
    const read = parseMoney(values[end] ?? '');
    if (read.ok && read.cents !== null) out[end] = read.cents;
  }
  for (const end of QUANTITY_ENDS) {
    const read = readQuantity(values[end] ?? '');
    if (read.ok && read.value !== null) out[end] = read.value;
  }
  if (PRODUCT_STATUSES.includes(values.status as ProductStatus)) out.status = values.status as ProductStatus;
  return out;
}

/** The filters that really apply (an end it cannot read does not). */
export function filtersInUse(values: DataTableFilters): number {
  return Object.keys(filterParams(values)).length;
}

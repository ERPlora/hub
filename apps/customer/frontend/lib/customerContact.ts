// A customer's email and phone reach only whoever sees the customers' contact details: anyone else gets them as null,
// and a list of the apps that show a customer's phone neither paints, sorts nor filters by it.
import type { DataTableColumn } from '@erplora/ui/components';

import { formatPhone } from './phoneDisplay';

export const CUSTOMER_CONTACT = 'base.view_customer_contact';

export interface PhoneColumn<K extends string> {
  /** The row's field with the phone. */
  key: K;
  label: string;
  /** The server filters the list by the digits typed in the column. */
  filtered?: boolean;
}

/** The «Phone» column for whoever `sees` it: as Customers paints it (+34 600 111 222), never sorted (the order would
 *  tell whose number comes first). */
export function phoneColumns<K extends string, Row extends Record<K, string | null>>(
  sees: boolean,
  column: PhoneColumn<K>,
): DataTableColumn<Row>[] {
  if (!sees) return [];
  const { key, label, filtered } = column;
  return [{ key, label, priority: 'low', format: (_, row) => formatPhone(row[key]), ...(filtered ? { filter: { type: 'text' } } : {}) }];
}

// A guest's phone and email reach only whoever sees the customers' contact details: anyone else gets them as null,
// and the book and the waitlist neither paint them nor search or filter by them.
import type { DataTableColumn } from '@erplora/ui/components';

import { formatPhone } from '../../../customer/frontend/lib/phoneDisplay';

export const CUSTOMER_CONTACT = 'base.view_customer_contact';

/** The «Phone» column for whoever `sees` it: as Customers paints it (+34 600 111 222), filtered by the server by its
 *  digits, never sorted (the order would tell whose number comes first). */
export function phoneColumns<Row extends { guest_phone: string | null }>(sees: boolean, label: string): DataTableColumn<Row>[] {
  if (!sees) return [];
  return [{ key: 'guest_phone', label, priority: 'low', format: (_, row) => formatPhone(row.guest_phone), filter: { type: 'text' } }];
}

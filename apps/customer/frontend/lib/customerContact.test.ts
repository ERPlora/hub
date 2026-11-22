import { describe, expect, it } from 'vitest';

import { CUSTOMER_CONTACT, phoneColumns } from './customerContact';

const row = { guest_phone: '+34600111222' as string | null };

describe('customerContact', () => {
  it('names the data permission of the customers’ contact details', () => {
    expect(CUSTOMER_CONTACT).toBe('base.view_customer_contact');
  });

  it('gives whoever sees the phone its column: painted as Customers does, never sorted', () => {
    const columns = phoneColumns<'guest_phone', typeof row>(true, { key: 'guest_phone', label: 'Phone' });
    expect(columns.map(({ key, label, sortable, priority, filter }) => ({ key, label, sortable, priority, filter }))).toEqual([
      { key: 'guest_phone', label: 'Phone', sortable: undefined, priority: 'low', filter: undefined },
    ]);
    expect(columns[0].format?.(row.guest_phone, row)).toBe('+34 600 111 222');
  });

  it('lets the server filter by its digits when the list does', () => {
    const [column] = phoneColumns<'guest_phone', typeof row>(true, { key: 'guest_phone', label: 'Phone', filtered: true });
    expect(column.filter).toEqual({ type: 'text' });
  });

  it('gives no column to whoever does not see it', () => {
    expect(phoneColumns<'guest_phone', typeof row>(false, { key: 'guest_phone', label: 'Phone', filtered: true })).toEqual([]);
  });
});

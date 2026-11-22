import { describe, expect, it } from 'vitest';

import { CUSTOMER_CONTACT, phoneColumns } from './guestContact';

const row = { guest_phone: '+34600111222' as string | null };

describe('guestContact', () => {
  it('names the data permission of the customers’ contact details', () => {
    expect(CUSTOMER_CONTACT).toBe('base.view_customer_contact');
  });

  it('gives whoever sees the phone its column: painted as Customers does, filtered by the server, never sorted', () => {
    const columns = phoneColumns<typeof row>(true, 'Phone');
    expect(columns.map(({ key, label, sortable, priority, filter }) => ({ key, label, sortable, priority, filter }))).toEqual([
      { key: 'guest_phone', label: 'Phone', sortable: undefined, priority: 'low', filter: { type: 'text' } },
    ]);
    expect(columns[0].format?.(row.guest_phone, row)).toBe('+34 600 111 222');
  });

  it('gives no column to whoever does not see it', () => {
    expect(phoneColumns<typeof row>(false, 'Phone')).toEqual([]);
  });
});

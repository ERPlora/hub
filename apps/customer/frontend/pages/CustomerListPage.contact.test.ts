// Customers → Customers and the customers' email and phone (CUSTOMER-F02, BASE-F119): the «Email» and «Phone» columns
// only for whoever sees the customers' contact details, never sortable, and a search box that says what it looks into.
import { DataTable } from '@erplora/ui/components';
import type { SessionMe } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { mountCustomer, OWNER, WITHOUT_CONTACT } from '../__tests__/mount-customer';
import CustomerListPage from './CustomerListPage.vue';

/** The table the page paints for `session`, in `locale`: its columns (key, sortable) and its search hint. */
async function painted(session: SessionMe, locale: 'en' | 'es' = 'en') {
  const page = await mountCustomer(CustomerListPage, { session, locale });
  await page.live();
  const prop = <T>(name: string) => (page.wrapper.findComponent(DataTable as unknown as Component).props() as Record<string, unknown>)[name] as T;
  const columns = prop<{ key: string; sortable?: boolean }[]>('columns').map((c) => [c.key, !!c.sortable]);
  return { columns, placeholder: prop<string>('searchPlaceholder') };
}

describe('CustomerListPage: the customers\' contact details', () => {
  it('whoever sees them has «Email» and «Phone», not sortable, and a search into them', async () => {
    const s = await painted(OWNER);
    expect(s.columns).toEqual([
      ['name', true],
      ['email', false],
      ['phone', false],
      ['lifecycle_stage', true],
      ['total_spent', true],
    ]);
    expect(s.placeholder).toBe('Search name, phone or email…');
  });

  it('whoever does not has neither column and a search into name, tax ID and company, in both languages', async () => {
    const s = await painted(WITHOUT_CONTACT);
    expect(s.columns.map(([key]) => key)).toEqual(['name', 'lifecycle_stage', 'total_spent']);
    expect(s.placeholder).toBe('Search name, tax ID or company…');
    expect((await painted(WITHOUT_CONTACT, 'es')).placeholder).toBe('Buscar nombre, NIF o empresa…');
  });
});

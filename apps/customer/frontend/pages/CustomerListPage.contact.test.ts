// Customers → Customers and the customers' email and phone (CUSTOMER-F02, BASE-F119): the «Email» and «Phone» columns
// only for whoever sees the customers' contact details, never sortable, and a search box that says what it looks into.
import { DataTable } from '@erplora/ui/components';
import { afterEach, describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { type MountOptions, mountCustomer, OWNER, WITHOUT_CONTACT } from '../__tests__/mount-customer';
import CustomerListPage from './CustomerListPage.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(CustomerListPage, { attachTo: document.body, ...options });
  await m.live();
  const prop = <T>(name: string) => (m.wrapper.findComponent(DataTable as unknown as Component).props() as Record<string, unknown>)[name] as T;
  const columns = () => prop<{ key: string; sortable?: boolean }[]>('columns').map((c) => [c.key, !!c.sortable]);
  return { ...m, columns, placeholder: () => prop<string>('searchPlaceholder') };
}

describe('CustomerListPage: the customers\' contact details', () => {
  it('whoever sees them has «Email» and «Phone», not sortable, and a search into them', async () => {
    const s = await setup({ session: OWNER });
    expect(s.columns()).toEqual([
      ['name', true],
      ['email', false],
      ['phone', false],
      ['lifecycle_stage', true],
      ['total_spent', true],
    ]);
    expect(s.placeholder()).toBe('Search name, phone or email…');
  });

  it('whoever does not has neither column and a search into name, tax ID and company, in both languages', async () => {
    const s = await setup({ session: WITHOUT_CONTACT });
    expect(s.columns().map(([key]) => key)).toEqual(['name', 'lifecycle_stage', 'total_spent']);
    expect(s.placeholder()).toBe('Search name, tax ID or company…');
    const es = await setup({ session: WITHOUT_CONTACT, locale: 'es' });
    expect(es.placeholder()).toBe('Buscar nombre, NIF o empresa…');
  });
});

// The searches behind the service forms' pickers (Combo): they ask the server what the person types
// (20 at a time) and turn each row into an option with what the person reads. The tax category's
// option is its key, named by its translated name and its rate («Service — generic · 21 %»); the
// others are ids.
import type { LiveClient } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { searchMembers, searchServiceCategories, searchServices, searchTaxCategories } from './pickers';

function client(rows: unknown[]) {
  const call = vi.fn().mockResolvedValue({ rows, total: rows.length, limit: 20, offset: 0 });
  return { client: { api: { call } } as unknown as LiveClient, call };
}

const t = (key: string) => ({ 'service.tax.exempt': 'exempt' })[key] ?? key;

describe('searchTaxCategories', () => {
  it('asks Taxes for the categories by their name and offers each by its name and rate', async () => {
    const { client: c, call } = client([
      { key: 'service.generic', display_name: 'Service — generic', rate_pct: '21.00', operation_class: 'subject' },
      { key: 'service.health', display_name: 'Service — healthcare', rate_pct: '0.00', operation_class: 'exempt' },
      { key: 'salon.new', display_name: 'New', rate_pct: null, operation_class: null },
    ]);
    const options = await searchTaxCategories(c, t, 'en')('serv');
    expect(call).toHaveBeenCalledWith('tax.category.list', { search: 'serv', limit: 20, sort: 'display_name' });
    expect(options).toEqual([
      { id: 'service.generic', label: 'Service — generic · 21%' },
      { id: 'service.health', label: 'Service — healthcare · exempt' },
      { id: 'salon.new', label: 'New' },
    ]);
  });

  it('opening the list asks without a search', async () => {
    const { client: c, call } = client([]);
    await searchTaxCategories(c, t, 'en')('');
    expect(call).toHaveBeenCalledWith('tax.category.list', { limit: 20, sort: 'display_name' });
  });
});

describe('searchServiceCategories', () => {
  it('offers the live categories with their parent as a hint', async () => {
    const { client: c, call } = client([{ id: 'c1', name: 'Colour', parent_name: 'Hair' }, { id: 'c2', name: 'Hair', parent_name: null }]);
    expect(await searchServiceCategories(c)('co')).toEqual([
      { id: 'c1', label: 'Colour', hint: 'Hair' },
      { id: 'c2', label: 'Hair' },
    ]);
    expect(call).toHaveBeenCalledWith('service.category.list', { search: 'co', limit: 20 });
  });
});

describe('searchServices', () => {
  it('offers the offered services with their price', async () => {
    const { client: c, call } = client([{ id: 's1', name: 'Cut', price: 2000 }]);
    expect(await searchServices(c, 'es')('cu')).toEqual([{ id: 's1', label: 'Cut', hint: expect.stringMatching(/^20,00\s€$/) }]);
    expect(call).toHaveBeenCalledWith('service.service.list', { search: 'cu', limit: 20 });
  });
});

describe('searchMembers', () => {
  it('offers the active professionals of Staff by their full name', async () => {
    const { client: c, call } = client([{ id: 'm1', full_name: 'Ana López', role_name: 'Stylist' }, { id: 'm2', full_name: 'Bea Ruiz', role_name: null }]);
    expect(await searchMembers(c)('a')).toEqual([
      { id: 'm1', label: 'Ana López', hint: 'Stylist' },
      { id: 'm2', label: 'Bea Ruiz' },
    ]);
    expect(call).toHaveBeenCalledWith('staff.member.list', { search: 'a', status: 'active', limit: 20 });
  });
});

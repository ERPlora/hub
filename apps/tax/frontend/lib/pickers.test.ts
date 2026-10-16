// The server search behind the Category filter of the tax lists (the table funnel's `lookup`): every
// category of the business, not a first page, by name, the first 50 matches of what is typed; the value
// is the category key and the label names it as the pickers do («Food (restaurant.food)»).
import { describe, expect, it, vi } from 'vitest';

import { categorySearch } from './pickers';

function client(rows: unknown[]) {
  const call = vi.fn(async () => ({ rows, total: rows.length, limit: 50, offset: 0 }));
  return { api: { call } } as unknown as Parameters<typeof categorySearch>[0] & { api: { call: typeof call } };
}

describe('categorySearch', () => {
  it('asks tax.category.list by name for what is typed; value the key, label the picker label', async () => {
    const c = client([{ key: 'restaurant.food', name: 'Food', display_name: 'Comida' }]);
    expect(await categorySearch(c)('com')).toEqual([{ value: 'restaurant.food', label: 'Comida (restaurant.food)' }]);
    expect(c.api.call).toHaveBeenCalledWith('tax.category.list', { search: 'com', sort: 'display_name', dir: 'asc', limit: 50 });
  });

  it('sends no search when nothing is typed', async () => {
    const c = client([]);
    expect(await categorySearch(c)('')).toEqual([]);
    expect(c.api.call).toHaveBeenLastCalledWith('tax.category.list', { sort: 'display_name', dir: 'asc', limit: 50 });
  });
});

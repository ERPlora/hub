// The server searches behind the staff pickers (SearchSelect): members by name, roles (all, or only
// the active ones a record may take) and the accounts of the business. Each asks for the first 100
// matches (the server's cap), sends the search only when there is one, and gives value + label.
import { describe, expect, it, vi } from 'vitest';

import { accountSearch, memberSearch, roleSearch } from './pickers';

function client(rows: unknown[]) {
  const call = vi.fn(async () => ({ rows, total: rows.length, limit: 100, offset: 0 }));
  return { api: { call } } as unknown as Parameters<typeof memberSearch>[0] & { api: { call: typeof call } };
}

describe('pickers', () => {
  it('members: by name, value the record id', async () => {
    const c = client([{ id: 'm1', full_name: 'Ana López' }]);
    expect(await memberSearch(c)('an')).toEqual([{ value: 'm1', label: 'Ana López' }]);
    expect(c.api.call).toHaveBeenCalledWith('staff.member.list', { sort: 'name', limit: 100, search: 'an' });
    await memberSearch(c)('');
    expect(c.api.call).toHaveBeenLastCalledWith('staff.member.list', { sort: 'name', limit: 100 });
  });

  it('roles: only the active ones for a record, or every one by name for a filter', async () => {
    const c = client([{ id: 'r1', name: 'Stylist' }]);
    expect(await roleSearch(c, { activeOnly: true, by: 'id' })('')).toEqual([{ value: 'r1', label: 'Stylist' }]);
    expect(c.api.call).toHaveBeenLastCalledWith('staff.role.list', { is_active: true, sort: 'name', limit: 100 });
    expect(await roleSearch(c, { activeOnly: false, by: 'name' })('sty')).toEqual([{ value: 'Stylist', label: 'Stylist' }]);
    expect(c.api.call).toHaveBeenLastCalledWith('staff.role.list', { sort: 'name', limit: 100, search: 'sty' });
  });

  it('accounts: value the user id as text', async () => {
    const c = client([{ user_id: 4, name: 'Ana López' }]);
    expect(await accountSearch(c)('')).toEqual([{ value: '4', label: 'Ana López' }]);
    expect(c.api.call).toHaveBeenLastCalledWith('staff.account.list', { limit: 100 });
  });
});

// Whose tip it is: the active team of Staff, asked through its own list as the person types, for the «For» filter of
// the Tips list and the person of «Adjust».
import type { LiveClient } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { teamFilter, teamSearch } from './team';

const TEAM = { rows: [{ id: 'm-bea', full_name: 'Bea Gil' }, { id: 'm-carla', full_name: 'Carla Ruiz' }], total: 2, limit: 20, offset: 0 };

function client() {
  const call = vi.fn(async () => TEAM);
  return { client: { api: { call } } as unknown as Pick<LiveClient, 'api'>, call };
}

describe('teamSearch', () => {
  it('asks Staff for the active team matching what is typed, trimmed, 20 at a time', async () => {
    const { client: api, call } = client();
    expect(await teamSearch(api)('  bea ')).toEqual([
      { id: 'm-bea', label: 'Bea Gil' },
      { id: 'm-carla', label: 'Carla Ruiz' },
    ]);
    expect(call).toHaveBeenCalledWith('staff.member.list', { search: 'bea', status: 'active', limit: 20 });
  });

  it('with nothing typed, the first ones', async () => {
    const { client: api, call } = client();
    await teamSearch(api)('');
    expect(call).toHaveBeenCalledWith('staff.member.list', { status: 'active', limit: 20 });
  });
});

describe('teamFilter', () => {
  it('gives the same people as the options of a filter: the record’s id, named by the person', async () => {
    const { client: api } = client();
    expect(await teamFilter(api)('b')).toEqual([
      { value: 'm-bea', label: 'Bea Gil' },
      { value: 'm-carla', label: 'Carla Ruiz' },
    ]);
  });
});

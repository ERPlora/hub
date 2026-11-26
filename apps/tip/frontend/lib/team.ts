// Whose tip it is: the active team of Staff (a requirement of Tips), read through Staff's own list as the person types.
import type { ComboOption, DataTableFilterOption } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

const PAGE = 20;

export function teamSearch(client: Pick<LiveClient, 'api'>): (query: string) => Promise<ComboOption[]> {
  return async (query) => {
    const text = query.trim();
    const team = await client.api.call('staff.member.list', { ...(text ? { search: text } : {}), status: 'active', limit: PAGE });
    return team.rows.map((member) => ({ id: member.id, label: member.full_name }));
  };
}

export function teamFilter(client: Pick<LiveClient, 'api'>): (query: string) => Promise<DataTableFilterOption[]> {
  const search = teamSearch(client);
  return async (query) => (await search(query)).map((option) => ({ value: option.id, label: option.label }));
}

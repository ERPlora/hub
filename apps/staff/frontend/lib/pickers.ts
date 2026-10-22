// The server searches behind the staff pickers: members by name, roles and the accounts of the
// business, for the table filters (the funnel's `lookup`, value + label) and, through `asCombo`, for the
// Combo fields of the forms. A business may have more than the 100 rows the server gives at once, so a
// picker never loads «all»: it asks for the first 100 matches of what the person types.
import type { ComboSearch, DataTableFilterOption } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

type Search = (search: string) => Promise<DataTableFilterOption[]>;

const LIMIT = 100;
const withSearch = (search: string) => (search ? { search } : {});

/** Staff members by name; the value is the record's id. */
export function memberSearch(client: Pick<LiveClient, 'api'>): Search {
  return async (search) => {
    const answer = await client.api.call('staff.member.list', { sort: 'name', limit: LIMIT, ...withSearch(search) });
    return answer.rows.map((member) => ({ value: member.id, label: member.full_name }));
  };
}

/** Roles by name: only the active ones (a record's role), or every one (a filter); valued by id or name. */
export function roleSearch(client: Pick<LiveClient, 'api'>, options: { activeOnly: boolean; by: 'id' | 'name' }): Search {
  return async (search) => {
    const answer = await client.api.call('staff.role.list', {
      ...(options.activeOnly ? { is_active: true } : {}),
      sort: 'name',
      limit: LIMIT,
      ...withSearch(search),
    });
    return answer.rows.map((role) => ({ value: options.by === 'id' ? role.id : role.name, label: role.name }));
  };
}

/** The active accounts with access to this business; the value is the user's id, as text. */
export function accountSearch(client: Pick<LiveClient, 'api'>): Search {
  return async (search) => {
    const answer = await client.api.call('staff.account.list', { limit: LIMIT, ...withSearch(search) });
    return answer.rows.map((account) => ({ value: String(account.user_id), label: account.name }));
  };
}

/** A search as a Combo's (`{ id, label }`, the typing trimmed), with an optional «none» choice — id
 *  `''`, «No role» — first while nothing is typed: the way to empty the field, as in the old select. */
export function asCombo(search: Search, none?: () => string): ComboSearch {
  return async (query) => {
    const text = query.trim();
    const found = (await search(text)).map(({ value, label }) => ({ id: value, label }));
    return none && text === '' ? [{ id: '', label: none() }, ...found] : found;
  };
}

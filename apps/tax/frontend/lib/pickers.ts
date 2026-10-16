// The server searches behind the category pickers: the Category filter of the tax lists (the table
// funnel's `lookup`) and the Category field of the rule and alias dialogs (a `Combo`). A business may
// have more categories than a list holds, so a picker never loads «all» — it asks for the first matches
// of what the person types, by name.
import type { ComboSearch, DataTableFilterOption } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

import { categoryDisplayName, categoryOptionLabel } from './rules';

const LIMIT = 50;

type Client = Pick<LiveClient, 'api'>;

function listCategories(client: Client, search: string) {
  const text = search.trim();
  return client.api.call('tax.category.list', {
    ...(text ? { search: text } : {}),
    sort: 'display_name',
    dir: 'asc',
    limit: LIMIT,
  });
}

/** Categories by name for a table filter; the value is the category key. */
export function categorySearch(client: Client): (search: string) => Promise<DataTableFilterOption[]> {
  return async (search) => {
    const answer = await listCategories(client, search);
    return answer.rows.map((category) => ({ value: category.key, label: categoryOptionLabel(category) }));
  };
}

/** Categories by name for a `Combo`: the option is the key, read by its name with the key as a hint. */
export function categoryCombo(client: Client): ComboSearch {
  return async (search) => {
    const answer = await listCategories(client, search);
    return answer.rows.map((category) => ({ id: category.key, label: categoryDisplayName(category), hint: category.key }));
  };
}

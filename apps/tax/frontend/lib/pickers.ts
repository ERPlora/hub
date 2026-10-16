// The server search behind the Category filter of the tax lists (the table funnel's `lookup`): a
// business may have more categories than a list holds, so the filter never loads «all» — it asks for
// the first matches of what the person types, by name.
import type { DataTableFilterOption } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

import { categoryOptionLabel } from './rules';

const LIMIT = 50;

/** Categories by name; the value is the category key. */
export function categorySearch(client: Pick<LiveClient, 'api'>): (search: string) => Promise<DataTableFilterOption[]> {
  return async (search) => {
    const answer = await client.api.call('tax.category.list', {
      ...(search ? { search } : {}),
      sort: 'display_name',
      dir: 'asc',
      limit: LIMIT,
    });
    return answer.rows.map((category) => ({ value: category.key, label: categoryOptionLabel(category) }));
  };
}

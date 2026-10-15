// The searches behind the task forms' pickers (`Combo` of @erplora/ui): each asks the server for what the
// person types, 20 at a time, and turns every row into an option. People come from Staff's own list (a
// required app, read through its operation, never its models); projects from this app's list.
import type { ComboOption, ComboSearch } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

/** Options asked at once: the person narrows them by typing. */
const PAGE = 20;

const search = (query: string) => (query.trim() ? { search: query.trim() } : {});
const withHint = (id: string, label: string, hint: string | null | undefined): ComboOption => (hint ? { id, label, hint } : { id, label });

/** The active people of the team, by name, with their role as hint. */
export function searchMembers(client: LiveClient): ComboSearch {
  return async (query) => {
    const page = await client.api.call('staff.member.list', { ...search(query), status: 'active', limit: PAGE });
    return page.rows.map((row) => withHint(row.id, row.full_name, row.role_name));
  };
}

/** The active projects, by name, with their code as hint. */
export function searchProjects(client: LiveClient): ComboSearch {
  return async (query) => {
    const page = await client.api.call('task.project.list', { ...search(query), is_active: true, limit: PAGE, sort: 'name' });
    return page.rows.map((row) => withHint(row.id, row.name, row.code));
  };
}

// A row of `base.app.list` for the tests of the Apps screen and its rules: on, chosen and free unless told otherwise.
import type { AppRow } from '../operations/apps';

export function app(id: string, fields: Partial<AppRow> = {}): AppRow {
  return {
    id,
    name: id[0].toUpperCase() + id.slice(1),
    icon: 'ion:cube-outline',
    category: 'sales',
    category_label: 'Sales, payments and tax',
    summary: `What ${id} does.`,
    premium: false,
    right: 'free',
    state: 'on',
    chosen: true,
    path: `/${id}/home`,
    requires: [],
    required_by: [],
    refusal: null,
    mandatory: false,
    ...fields,
  };
}

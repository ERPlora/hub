// Which columns the Apps catalog («Add apps») shows for the screen it is on (hub#2245).
//
// The list view lays every column side by side, each at least 88 px (OutfitKit's readable floor).
// On a phone the catalog's six columns came to ~600 px on a 358 px table: app, version and a
// clipped category were all a person saw, and status and the row's action sat off to the right
// with nothing saying the table scrolls. Condensed like Shopify's index table on a phone: the list
// keeps which app it is and whether it is there, and the table pins the row's action on its own.
// The card view stacks fields instead of laying them side by side, so it keeps all of them.

export type TableView = 'table' | 'cards';

/**
 * ok-data-table's own phone step (`MOBILE_BREAKPOINT`, 640 px). Below it the table folds its row
 * actions into «More actions» and starts on cards; the page condenses the list at the same width so
 * the two never disagree about what a phone is.
 */
export const TABLE_PHONE_QUERY = '(max-width: 640px)';

/** What the catalog's narrow list view keeps: the app, and its status. */
const NARROW_LIST_KEYS = new Set(['name', 'stateLabel']);

export function columnsForScreen<T extends { key: string }>(
  columns: T[],
  screen: { compact: boolean; view: TableView },
): T[] {
  if (!screen.compact || screen.view !== 'table') return columns;
  return columns.filter((c) => NARROW_LIST_KEYS.has(c.key));
}

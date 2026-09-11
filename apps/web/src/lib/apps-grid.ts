// The «My apps» grid on a phone (hub#1197).
//
// With 25+ installed apps the launcher's auto-fill grid ran to 7 rows at 390px — 26 tiles at 3
// per row — and that alone, together with the setup checklist above the widget board, put the
// board 2.6 SCREENS down before a single KPI painted. What every launcher on the market does once
// the list outgrows the screen — macOS Launchpad's pages, the Android app drawer's «see all», the
// Play Store's collapsed rows — is show a first taste and a deliberate way to see the rest; none of
// them grow the surface to fit everything at once.
//
// This module owns the FOLD, not the paint: given the ordered list `MyAppsCard.vue` already built
// (most-used-first, `orderAppsByUsage`) and whether the viewport is a phone, which tiles does the
// grid show and how many stayed behind. Same split as the sibling card's `checklistView`
// (`setup-status.ts`) — a pure function the component turns into a «View all apps» tile.

/**
 * Columns on a phone, fixed by `MyAppsCard.vue`'s own `@media (max-width: 540px)` step instead of
 * left to the desktop grid's `auto-fill` (measured in Chromium: 3 is what `auto-fill` already gives
 * at 390px with today's `minmax(5.5rem, 1fr)`, so pinning it here changes nothing at that width —
 * it only keeps the count from drifting to 4-5 as the viewport approaches 540px, which the fold
 * below has to be able to rely on).
 */
export const PHONE_GRID_COLUMNS = 3;

/** Rows the grid is allowed on a phone — hub#1197's own measurement was 7; this is 2. */
export const PHONE_VISIBLE_ROWS = 2;

/**
 * The grid's cell budget on a phone: `PHONE_GRID_COLUMNS × PHONE_VISIBLE_ROWS`, and it is a budget
 * for the WHOLE grid, not for the app tiles alone.
 *
 * `MyAppsCard.vue` always paints a ＋ Add apps tile after whatever this module returns, and paints a
 * «View all apps» tile too whenever `hidden > 0` — both are cells of the SAME grid. A cap that only
 * counted app tiles let those trailing tiles push the card past its own row budget: capping at a
 * fixed 8 app tiles put `8 app tiles + view-all + add = 10 cells` on 4 rows of a 3-column grid, not
 * the 2 the issue asked for. Reserving their cells up front is what makes "2 rows" a fact about the
 * card, not an approximation of the app tiles inside it.
 */
const GRID_BUDGET = PHONE_GRID_COLUMNS * PHONE_VISIBLE_ROWS;

/** The ＋ Add apps tile never folds away — its cell is always spent. */
const ADD_TILE_CELLS = 1;

/** The «View all apps» tile costs a cell of its own, and only exists once folding is needed. */
const VIEW_ALL_TILE_CELLS = 1;

/**
 * Placeholder tiles the grid holds while the list is still on its way (hub#1722).
 *
 * Derived from the SAME budget the real tiles obey, not picked by eye: the skeleton stands in for
 * the grid that is coming, so a card that runs to three rows while loading and then settles back to
 * two would be its own defect — the panel would jump under the finger of whoever is reading it. The
 * ＋ Add apps tile is painted in every state, loading included, so its cell is spent here too.
 */
export const SKELETON_TILE_COUNT = GRID_BUDGET - ADD_TILE_CELLS;

export interface AppsGridView<T> {
  /** The tiles to render right now, in the caller's own order. */
  tiles: readonly T[];
  /** How many more installed apps exist behind «View all apps». */
  hidden: number;
}

/**
 * What the grid paints for this list. Off the phone (`isPhone: false`) nothing folds — the desktop
 * grid already handles any count via `auto-fill` (hub#1284 confirmed the columns hold at 1440/834).
 */
export function appsGridView<T>(apps: readonly T[], isPhone: boolean): AppsGridView<T> {
  if (!isPhone) return { tiles: apps, hidden: 0 };

  // Does the whole list fit beside the ＋ tile, with no fold at all?
  const noFoldCap = GRID_BUDGET - ADD_TILE_CELLS;
  if (apps.length <= noFoldCap) return { tiles: apps, hidden: 0 };

  // It does not: the fold needs its OWN cell too.
  const foldedCap = GRID_BUDGET - ADD_TILE_CELLS - VIEW_ALL_TILE_CELLS;
  return { tiles: apps.slice(0, foldedCap), hidden: apps.length - foldedCap };
}

// The «My apps» grid on a phone (hub#1197).
//
// With 25+ installed apps the launcher's auto-fill grid ran to 7 rows at 390px, and together with
// the setup checklist that put the widget board 2.6 SCREENS down before a single KPI painted. What
// every launcher on the market does when the list is longer than the screen — macOS Launchpad's
// pages, the Android app drawer's «see all», iOS's second home screen — is show a first taste and a
// deliberate way to see the rest, never grow the surface to fit everything at once.
//
// This file owns the FOLD, not the paint: given the ordered list of apps and whether the viewport is
// a phone, which ones does the grid show and how many stayed behind. `MyAppsCard.vue` is the one
// place that turns `hidden` into the «View all apps» tile — this is the pure decision behind it, the
// same split `checklistView` (`setup-status.ts`) already uses for the sibling card.
//
// The cap is a BUDGET, not a tile count: `MyAppsCard.vue` pins the grid to `PHONE_GRID_COLUMNS`
// columns at the same breakpoint (its own `@media (max-width: 540px)`), and the ＋ Add apps tile —
// never folded, always present — and a folding «View all» tile both take a cell in that SAME grid.
// A fixed tile count would let those trailing tiles push the card past its own row budget; measured
// in Chromium over the real card (390×844, 25 apps), that is exactly what a naive cap did: 8
// tiles + view-all + add landed on 4 rows in the natural 3-column grid, not 2. Reserving their cells
// up front is what makes «PHONE_VISIBLE_ROWS rows» a fact about the WHOLE grid instead of about the
// app tiles alone.
import { describe, expect, it } from 'vitest';
import { PHONE_GRID_COLUMNS, PHONE_VISIBLE_ROWS, appsGridView } from './apps-grid';

const apps = (n: number): { path: string }[] =>
  Array.from({ length: n }, (_, i) => ({ path: `/m/app-${i}` }));

// The grid budget MyAppsCard.vue actually has to work with: `PHONE_GRID_COLUMNS` columns forced by
// its stylesheet, `PHONE_VISIBLE_ROWS` rows tall.
const BUDGET = PHONE_GRID_COLUMNS * PHONE_VISIBLE_ROWS;
// The ＋ Add apps tile is not part of `apps` — MyAppsCard.vue paints it separately — but it lives in
// the SAME grid and never folds, so one cell of the budget is always spoken for.
const ADD_TILE = 1;

describe('what the grid shows on a phone', () => {
  it('a list that fits with the ＋ tile does not fold at all', () => {
    const view = appsGridView(apps(BUDGET - ADD_TILE), true);

    expect(view.tiles).toHaveLength(BUDGET - ADD_TILE);
    expect(view.hidden).toBe(0);
  });

  it('one app more than that no longer fits beside ＋ — the fold has to reserve its OWN cell too', () => {
    // hub#1197's own read of a naive cap: reserving only the ＋ tile's cell and not the fold's own
    // let `apps tiles + view-all + add` spill to a THIRD row of the 3-column grid — 8 + 1 + 1 = 10
    // cells, `Math.ceil(10 / 3) = 4` rows, not the 2 the issue asked for.
    const view = appsGridView(apps(BUDGET - ADD_TILE + 1), true);

    // Whatever it shows, `tiles + view-all(1) + add(1)` must fit inside the row budget.
    const totalCells = view.tiles.length + (view.hidden > 0 ? 1 : 0) + ADD_TILE;
    expect(totalCells).toBeLessThanOrEqual(BUDGET);
    expect(Math.ceil(totalCells / PHONE_GRID_COLUMNS)).toBeLessThanOrEqual(PHONE_VISIBLE_ROWS);
  });

  it('folds a long list down to the budget that leaves room for view-all AND ＋ (hub#1197)', () => {
    const view = appsGridView(apps(25), true);

    // Two cells are reserved (the fold's own tile, the ＋ tile that never folds).
    expect(view.tiles).toHaveLength(BUDGET - ADD_TILE - 1);
    expect(view.hidden).toBe(25 - view.tiles.length);
  });

  it('never hides a tile it does not have to: a short list is not folded', () => {
    const view = appsGridView(apps(3), true);

    expect(view.tiles).toHaveLength(3);
    expect(view.hidden).toBe(0);
  });

  it("keeps the caller's own order — the fold slices, it never re-sorts", () => {
    const ordered = apps(25);

    const view = appsGridView(ordered, true);

    expect(view.tiles).toEqual(ordered.slice(0, view.tiles.length));
  });

  it('the whole grid — apps shown, the fold tile, and ＋ Add apps — never exceeds the row budget', () => {
    // hub#1197's own measurement: 26 tiles (25 apps + ＋) read as 7 rows at 390px. This is the
    // invariant that number had to satisfy and did not.
    for (const n of [0, 1, BUDGET - ADD_TILE, BUDGET - ADD_TILE + 1, 9, 25, 60]) {
      const view = appsGridView(apps(n), true);
      const totalCells = view.tiles.length + (view.hidden > 0 ? 1 : 0) + ADD_TILE;

      expect(Math.ceil(totalCells / PHONE_GRID_COLUMNS)).toBeLessThanOrEqual(PHONE_VISIBLE_ROWS);
    }
  });
});

describe('off the phone, nothing folds', () => {
  it('a wide viewport shows every installed app, however many there are', () => {
    const view = appsGridView(apps(25), false);

    expect(view.tiles).toHaveLength(25);
    expect(view.hidden).toBe(0);
  });
});

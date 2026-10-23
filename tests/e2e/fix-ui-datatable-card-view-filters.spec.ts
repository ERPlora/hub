// flow: UI DataTable filtros en tarjetas — FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390 (seen by the worker of
// FIX-UI-TOPBAR-LONG-APP-NAME-390): at 390×844, where Cart & Checkout › Carts paints cards, its column filters
// (Session, Email, Status and the From/To ranges) sat open under the toolbar, each of its own width: half the
// screen before the first card. As in the old hub (docs/reference/old-hub/cart_checkout-carts-390.png), in the
// cards they wait behind the funnel next to list/cards and «New cart»: it opens the modal sheet (outfitkit#75)
// with those controls, the ranges inside it (saas#558); «Apply» filters the cards, closes the sheet
// (outfitkit#207) and the funnel counts 1. With ui 0c21d14 the row was open in the cards.
// Since FIX-HUB-CART-CHECKOUT-ORDERS-FILTERS-BEHIND-FUNNEL (CART_CHECKOUT-F12) Carts is `filterable` as the old list
// (cart_checkout-carts-{834,1440}.png): the wide list (1440) has no row either, its panel filters and switching to
// the cards and back keeps the filter in use; at 834, whatever paints by default, the filters wait behind the funnel.
// The rule for a list that keeps its filter row (not `filterable`) is measured since then on Modifiers › Groups (its
// Name filter is a text box, as Carts' Session was): at 1440 the list opens the row, the cards fold it behind the
// funnel with the filter in use (count 1) and back in the list the row shows it; at 834 each view follows the rule.
import { type Page, expect, test } from '@playwright/test';

import { psql, record, shot, shown, untilStill } from './helpers';
import { type Cart, cleanUp, code, listShown, post, rowOf, signedIn, VIEWPORTS } from './cart-checkout-helpers';

const TABLE = 'cart-checkout-carts';
const FILTERS = ['session_token', 'customer_email', 'status', 'total_items_from', 'total_items_to', 'total_amount_from', 'total_amount_to'];

test.beforeEach(cleanUp);
test.afterAll(cleanUp);

const hook = (page: Page, suffix: string) => shown(page).locator(`[data-testid=${TABLE}-${suffix}]`);
const cardsPainted = (page: Page) => shown(page).locator('.data-table__card');

/** How tall the table's toolbar is (search, buttons and, when open, the filter row) and its filter row. */
async function toolbar(page: Page): Promise<{ bar: number; row: number }> {
  return shown(page)
    .locator('.data-table')
    .first()
    .evaluate((root) => ({
      bar: Math.round(root.querySelector('.data-table__bar')?.getBoundingClientRect().height ?? 0),
      row: Math.round(root.querySelector('.data-table__filters')?.getBoundingClientRect().height ?? 0),
    }));
}

/** Two carts of this run, through the API (the assistant's path): the filters have something to tell apart. */
async function seed(context: Parameters<typeof post>[0], width: number): Promise<{ one: Cart; two: Cart }> {
  const one = await post<Cart>(context, '/cart_checkout/carts', { session_token: code(`fold-one-${width}`), customer_email: 'ana@example.com' }, 201);
  const two = await post<Cart>(context, '/cart_checkout/carts', { session_token: code(`fold-two-${width}`), customer_email: 'bea@example.com' }, 201);
  return { one, two };
}

test('UI DataTable filtros en tarjetas at 390: the filters wait behind the funnel, its sheet filters the cards and the funnel counts 1', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/cart_checkout/carts', VIEWPORTS.phone);
  try {
    const { one, two } = await seed(context, 390);
    await page.goto('/cart_checkout/carts');
    await listShown(page, TABLE);
    await expect(rowOf(page, TABLE, one.id)).toBeVisible();
    await expect(cardsPainted(page).first(), 'a phone paints cards').toBeVisible();

    const folded = await toolbar(page);
    record('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-390', folded);
    await expect(hook(page, 'filters'), `no filter row open in the cards (it took ${folded.row} px)`).toHaveCount(0);
    expect(folded.bar, 'the toolbar is search and buttons, not half the screen').toBeLessThan(844 / 4);
    const funnel = hook(page, 'filters-toggle');
    await expect(funnel).toBeVisible();
    await expect(hook(page, 'filters-count')).toHaveCount(0);
    await page.screenshot({ path: shot('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-390') });

    await funnel.click();
    const sheet = hook(page, 'filters-panel');
    await expect(sheet).toBeVisible();
    await expect(sheet, 'on a phone the panel is the modal sheet (outfitkit#75)').toHaveAttribute('aria-modal', 'true');
    // It slides in (0.18 s): measured once it stands still.
    await untilStill(page);
    const box = (await sheet.boundingBox())!;
    for (const name of FILTERS) {
      const control = sheet.locator(`[data-testid=${TABLE}-filter-${name}]`);
      await expect(control, `${name} is in the sheet`).toBeVisible();
      const own = (await control.boundingBox())!;
      // saas#558: a range's From/To fits the sheet, nothing runs past its edge.
      expect(own.x, `${name} starts inside the sheet`).toBeGreaterThanOrEqual(box.x - 0.5);
      expect(own.x + own.width, `${name} ends inside the sheet`).toBeLessThanOrEqual(box.x + box.width + 0.5);
    }
    await page.screenshot({ path: shot('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-390-sheet') });

    await sheet.locator(`[data-testid=${TABLE}-filter-session_token] input`).fill(one.session_token);
    // A draft: nothing filters until «Apply».
    await expect(rowOf(page, TABLE, two.id)).toBeAttached();
    await hook(page, 'filters-apply').click();
    await expect(sheet, '«Apply» closes the sheet and shows the result (outfitkit#207)').toBeHidden();
    await expect(rowOf(page, TABLE, one.id)).toBeVisible();
    await expect(rowOf(page, TABLE, two.id)).toHaveCount(0);
    await expect(hook(page, 'filters-count')).toHaveText('1');
    await expect(hook(page, 'filters')).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test('UI DataTable filtros en tarjetas at 1440: the list keeps its filters behind the funnel too; the cards keep the filter in use', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/cart_checkout/carts', VIEWPORTS.desktop);
  try {
    const { one, two } = await seed(context, 1440);
    await page.goto('/cart_checkout/carts');
    await listShown(page, TABLE);
    await expect(rowOf(page, TABLE, one.id)).toBeVisible();
    await expect(cardsPainted(page), 'a wide screen paints the list').toHaveCount(0);

    const row = hook(page, 'filters');
    await expect(row, 'no filter row: Carts filters behind the funnel, as the old list').toHaveCount(0);
    const funnel = hook(page, 'filters-toggle');
    await expect(funnel).toBeVisible();
    await page.screenshot({ path: shot('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-1440') });

    await funnel.click();
    const panel = hook(page, 'filters-panel');
    await expect(panel).toBeVisible();
    await expect(panel, 'on a wide screen the panel sits inside the table, not over it').not.toHaveAttribute('aria-modal', 'true');
    await panel.locator(`[data-testid=${TABLE}-filter-session_token] input`).fill(one.session_token);
    await hook(page, 'filters-apply').click();
    await expect(panel).toBeHidden();
    await expect(rowOf(page, TABLE, two.id)).toHaveCount(0);
    await expect(rowOf(page, TABLE, one.id)).toBeVisible();

    await hook(page, 'view-cards').click();
    await expect(cardsPainted(page).first()).toBeVisible();
    await expect(row).toHaveCount(0);
    await expect(hook(page, 'filters-count'), 'the filter in use is kept').toHaveText('1');
    await expect(rowOf(page, TABLE, one.id)).toBeVisible();
    await expect(rowOf(page, TABLE, two.id)).toHaveCount(0);

    await hook(page, 'view-table').click();
    await expect(cardsPainted(page)).toHaveCount(0);
    await expect(row).toHaveCount(0);
    await expect(hook(page, 'filters-count')).toHaveText('1');
    await expect(rowOf(page, TABLE, two.id)).toHaveCount(0);
    await funnel.click();
    await expect(panel.locator(`[data-testid=${TABLE}-filter-session_token] input`)).toHaveValue(one.session_token);
    await hook(page, 'filters-close').click();
    await expect(panel).toBeHidden();
    // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  } finally {
    await context.close();
  }
});

test('UI DataTable filtros en tarjetas at 834: whatever paints by default, the filters wait behind the funnel', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/cart_checkout/carts', VIEWPORTS.tablet);
  try {
    const { one } = await seed(context, 834);
    await page.goto('/cart_checkout/carts');
    await listShown(page, TABLE);
    await expect(rowOf(page, TABLE, one.id)).toBeVisible();
    const cards = (await cardsPainted(page).count()) > 0;
    record('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-834', { cards, ...(await toolbar(page)) });
    await expect(hook(page, 'filters'), `no filter row (${cards ? 'cards' : 'list'})`).toHaveCount(0);
    await expect(hook(page, 'filters-toggle')).toBeVisible();
    await page.screenshot({ path: shot('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-834') });
  } finally {
    await context.close();
  }
});

// ── A list that keeps its filter row: Modifiers › Groups ─────────────────────────────────────────────────────
const ROW_TABLE = 'modifier-groups';
/** Every group these cases create starts like this (and only those are deleted). */
const GROUPS = 'E2E Fold';
const rowHook = (page: Page, suffix: string) => shown(page).locator(`[data-testid=${ROW_TABLE}-${suffix}]`);

function cleanGroups(): void {
  psql(`delete from modifier_modifiergroup where name like '${GROUPS} %'`);
}
test.beforeEach(cleanGroups);
test.afterAll(cleanGroups);

interface Group {
  id: string;
  name: string;
}

/** Two groups of this run, through the API (the assistant's path): the Name filter has something to tell apart. */
async function seedGroups(context: Parameters<typeof post>[0], width: number): Promise<{ one: Group; two: Group }> {
  const stamp = Date.now().toString(36);
  const one = await post<Group>(context, '/modifier/groups', { name: `${GROUPS} one ${width} ${stamp}` }, 201);
  const two = await post<Group>(context, '/modifier/groups', { name: `${GROUPS} two ${width} ${stamp}` }, 201);
  return { one, two };
}

test('UI DataTable filtros en tarjetas at 1440: a list with its filter row keeps it open; the cards fold it and keep the filter in use', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/modifier/groups', VIEWPORTS.desktop);
  try {
    const { one, two } = await seedGroups(context, 1440);
    await page.goto('/modifier/groups');
    await expect(rowOf(page, ROW_TABLE, one.id)).toBeVisible();
    await expect(cardsPainted(page), 'a wide screen paints the list').toHaveCount(0);

    const row = rowHook(page, 'filters');
    await expect(row, 'the list keeps its filter row open').toBeVisible();
    await expect(rowHook(page, 'filters-toggle')).toHaveCount(0);
    await page.screenshot({ path: shot('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-1440-row') });

    await row.locator(`[data-testid=${ROW_TABLE}-filter-name] input`).fill(one.name);
    await expect(rowOf(page, ROW_TABLE, two.id)).toHaveCount(0);
    await expect(rowOf(page, ROW_TABLE, one.id)).toBeVisible();

    await rowHook(page, 'view-cards').click();
    await expect(cardsPainted(page).first()).toBeVisible();
    await expect(row, 'the cards fold the row').toHaveCount(0);
    await expect(rowHook(page, 'filters-toggle'), 'behind the funnel').toBeVisible();
    await expect(rowHook(page, 'filters-count'), 'the filter in use is kept').toHaveText('1');
    await expect(rowOf(page, ROW_TABLE, one.id)).toBeVisible();
    await expect(rowOf(page, ROW_TABLE, two.id)).toHaveCount(0);

    await rowHook(page, 'view-table').click();
    await expect(cardsPainted(page)).toHaveCount(0);
    await expect(row, 'back in the list the row opens again').toBeVisible();
    await expect(row.locator(`[data-testid=${ROW_TABLE}-filter-name] input`)).toHaveValue(one.name);
    await expect(rowOf(page, ROW_TABLE, two.id)).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test('UI DataTable filtros en tarjetas at 834: on a list with its filter row each view follows the rule (the cards fold it, the list opens it)', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/modifier/groups', VIEWPORTS.tablet);
  try {
    const { one } = await seedGroups(context, 834);
    await page.goto('/modifier/groups');
    await expect(rowOf(page, ROW_TABLE, one.id)).toBeVisible();
    const first = (await cardsPainted(page).count()) > 0 ? 'cards' : 'table';
    record('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-834-row', { first, ...(await toolbar(page)) });
    await page.screenshot({ path: shot('FIX-UI-DATATABLE-CARD-VIEW-FILTERS-OPEN-390-834-row') });
    // What paints by default, then the other view: both follow the rule.
    for (const view of [first, first === 'cards' ? 'table' : 'cards']) {
      if (view !== first) await rowHook(page, `view-${view}`).click();
      if (view === 'cards') {
        await expect(cardsPainted(page).first()).toBeVisible();
        await expect(rowHook(page, 'filters'), 'the cards fold the row').toHaveCount(0);
        await expect(rowHook(page, 'filters-toggle')).toBeVisible();
      } else {
        await expect(cardsPainted(page)).toHaveCount(0);
        await expect(rowHook(page, 'filters'), 'the list opens the row').toBeVisible();
        await expect(rowHook(page, 'filters-toggle')).toHaveCount(0);
      }
    }
  } finally {
    await context.close();
  }
});

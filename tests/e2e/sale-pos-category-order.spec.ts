// flow: SALE-F01, INVENTORY-F08 — the till's category strip follows the position the business gave each category, not
// the alphabet: «Drinks · Wine and beer · Coffees» with those positions, and a tie goes by name. A new position given
// as the assistant gives it (`inventory.category.update` with `order`) moves the category in a till already open,
// without a reload. What this file creates is deleted after it; the cash register goes back as it was.
import { expect, type BrowserContext, type Page, test } from '@playwright/test';

import { A, api, login, shown } from './helpers';
import { cleanInventory, stamp } from './inventory-helpers';
import { drawerOff, restoreDrawer } from './sale-helpers';

const RUN = stamp();
/** Each category of this run by its id, named without the run's tag. */
const made = new Map<string, string>();

async function category(context: BrowserContext, name: string, order: number): Promise<string> {
  const res = await api<{ id: string }>(context, A, 'POST', '/inventory/categories', { name: `E2E ${name} ${RUN}`, order });
  expect(res.status, name).toBe(201);
  made.set(res.data.id, name);
  return res.data.id;
}

/** This run's categories in the order the till's strip shows them. */
async function strip(page: Page): Promise<string[]> {
  const ids = await shown(page)
    .locator('[data-testid^=pos-category-]')
    .evaluateAll((tabs) => tabs.map((tab) => (tab.getAttribute('data-testid') ?? '').replace('pos-category-', '')));
  return ids.flatMap((id) => made.get(id) ?? []);
}

test.afterAll(() => {
  cleanInventory();
  restoreDrawer();
});

test('the till shows the categories in their position, ties by name, and follows a new position live', async ({ page, context }) => {
  await login(page, A, '/inventory/categories');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  const coffees = await category(context, 'Coffees', 3);
  await category(context, 'Wine and beer', 2);
  await category(context, 'Drinks', 1);
  await category(context, 'Beer on tap', 2);

  await page.goto('/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await expect.poll(() => strip(page)).toEqual(['Drinks', 'Beer on tap', 'Wine and beer', 'Coffees']);

  const moved = await api(context, A, 'POST', '/inventory/categories/update', { id: coffees, order: 1 });
  expect(moved.status, 'Coffees to position 1').toBe(200);
  await expect.poll(() => strip(page)).toEqual(['Coffees', 'Drinks', 'Beer on tap', 'Wine and beer']);
});

// flow: KITCHEN-F01, KITCHEN-F02, KITCHEN-F03, KITCHEN-F04 — Kitchen → Stations in Chrome, by hand, with the real
// Inventory app: «Add station» creates one (a name another live station has is refused inside the panel); a tap on
// its row edits, renames and deactivates it; «Route» sends a product and a category of the catalogue to a station
// and «Remove» takes a route away; «Delete» asks first, refuses a station with routes and deletes it once it has
// none. The list keeps its rows on a phone and on a tablet (hub#2327, kitchen#131) and the panel has one main button
// (kitchen#121). Each screen in 390×844, 834×1112 and 1440×900 (`APP-KITCHEN-<flow>-<size>`). What a run creates —
// stations «E2E KST <run> …», products `E2E-KST-<run>-…` and the category «E2E KST <run>» — is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { stamp } from './sale-helpers';
import { ownerPage, pick, rowAction, settled } from './service-helpers';

const RUN = stamp();
const TAG = `E2E KST ${RUN}`;
const GRILL = `${TAG} Grill`;
const BAR = `${TAG} Bar`;
const CATEGORY = `${TAG} Drinks`;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

let burger: Product;

function cleanRun(): void {
  const stations = "select id from kitchen_station where name like 'E2E KST %'";
  psql(
    [
      `delete from kitchen_productroute where station_id in (${stations}) or product_id in (select id from inventory_product where sku like 'E2E-KST-%')`,
      `delete from kitchen_categoryroute where station_id in (${stations}) or category_id in (select id from inventory_category where name like 'E2E KST %')`,
      `update kitchen_ticketitem set station_id = null where station_id in (${stations})`,
      `delete from kitchen_station where id in (${stations})`,
    ].join('; '),
  );
}

async function stationId(context: BrowserContext, name: string): Promise<string> {
  const res = await api<{ rows: { id: string; name: string }[] }>(context, A, 'GET', `/kitchen/stations?search=${encodeURIComponent(name)}&limit=10`);
  expect(res.status).toBe(200);
  const found = res.data.rows.find((row) => row.name === name);
  expect(found, `station ${name}`).toBeTruthy();
  return found!.id;
}

/** Picks `text` in an `ion-select` (popover interface). */
async function choose(page: Page, select: Locator, text: string): Promise<void> {
  await select.click();
  await page.locator('ion-popover.select-popover ion-radio').filter({ hasText: new RegExp(`^\\s*${text}\\s*$`) }).click();
  await page.locator('ion-popover.select-popover').waitFor({ state: 'detached' });
}

const row = (page: Page, name: string): Locator => shown(page).locator('[data-testid=kitchen-stations-row]').filter({ hasText: name }).first();
const route = (page: Page, text: string): Locator => shown(page).locator('[data-testid=kitchen-routing-row]').filter({ hasText: text }).first();

async function capture(page: Page, flow: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    await page.screenshot({ path: shot(`APP-KITCHEN-${flow}-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.beforeAll(async ({ browser }) => {
  cleanRun();
  cleanInventory();
  const { context } = await ownerPage(browser, '/kitchen/stations');
  burger = await createProduct(context, { name: `${TAG} Burger`, sku: `E2E-KST-${RUN}-BUR`, price: 1200, tax_category_key: 'restaurant.food' });
  const category = await api(context, A, 'POST', '/inventory/categories', { name: CATEGORY });
  expect(category.status, JSON.stringify(category.data)).toBe(201);
  await context.close();
});

test.afterAll(() => {
  cleanRun();
  cleanInventory();
});

test('KITCHEN-F01, F02: «Add station» creates one, a taken name is refused in the panel, and a tap on its row edits it', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/stations', { width: 1440, height: 900 });
  try {
    const view = shown(page);
    await view.locator('[data-testid=kitchen-stations-primary-action]').click();
    const form = page.locator('ion-modal[data-testid=kitchen-station-form]');
    await expect(form).toBeVisible();
    // kitchen#121: the panel has one main button, its own.
    await expect(form.locator('[data-testid=kitchen-station-form-submit]')).toHaveText('Create station');
    await form.locator('[data-testid=kitchen-station-form-name] input').fill(GRILL);
    await choose(page, form.locator('[data-testid=kitchen-station-form-printer_usage]'), 'Bar');
    await capture(page, 'KITCHEN-F01', async () => {
      await expect(form.locator('[data-testid=kitchen-station-form-submit]')).toBeInViewport();
    });
    await form.locator('[data-testid=kitchen-station-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(row(page, GRILL)).toContainText('Screen and paper');
    await expect(row(page, GRILL)).toContainText('Bar');
    await expect(row(page, GRILL)).toContainText('Yes');

    // The same name again is refused inside the panel, which stays open.
    await view.locator('[data-testid=kitchen-stations-primary-action]').click();
    await form.locator('[data-testid=kitchen-station-form-name] input').fill(GRILL);
    await form.locator('[data-testid=kitchen-station-form-submit]').click();
    await expect(form.locator('[data-testid=kitchen-station-form-error]')).toContainText('There is already a station with that name.');
    await form.locator('[data-testid=kitchen-station-form-name] input').fill(BAR);
    await form.locator('[data-testid=kitchen-station-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(row(page, BAR)).toBeVisible();

    // hub#2327, kitchen#131: on a phone and on a tablet the list keeps its rows in view.
    // The station's colour stays beside its name however narrow the column (it shrank to nothing at 834 and 390).
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await row(page, GRILL).scrollIntoViewIfNeeded();
      await expect(row(page, GRILL)).toBeInViewport();
      const dot = await row(page, GRILL).locator('.kitchen-stations__dot').boundingBox();
      expect(dot?.width ?? 0, `${size.label}: the colour dot keeps its size`).toBeGreaterThan(8);
    }
    // kitchen#131: on a tablet or a phone on its side, editing a station keeps the list with its rows (it shrank
    // to the toolbar while the edit box was open).
    for (const size of [{ width: 1024, height: 600 }, { width: 844, height: 390 }, { width: 667, height: 375 }]) {
      await page.setViewportSize(size);
      await row(page, GRILL).click();
      await expect(form.locator('[data-testid=kitchen-station-form-name] input')).toHaveValue(GRILL);
      await form.locator('[data-testid=kitchen-station-form-cancel]').click();
      await expect(form).toBeHidden();
      await row(page, BAR).scrollIntoViewIfNeeded();
      await expect(row(page, BAR), `${size.width}×${size.height}`).toBeInViewport();
      const box = await row(page, BAR).boundingBox();
      expect(box?.height ?? 0, `${size.width}×${size.height}: the row keeps its height`).toBeGreaterThan(20);
    }
    await page.setViewportSize({ width: 1440, height: 900 });

    // KITCHEN-F02: a tap on the row opens «Edit station»; renamed and deactivated.
    await row(page, BAR).click();
    await expect(form.locator('[data-testid=kitchen-station-form-name] input')).toHaveValue(BAR);
    await form.locator('[data-testid=kitchen-station-form-name] input').fill(`${BAR} 2`);
    await form.locator('[data-testid=kitchen-station-form-is_active]').click();
    await capture(page, 'KITCHEN-F02', async () => {
      await expect(form.locator('[data-testid=kitchen-station-form-submit]')).toBeInViewport();
    });
    await expect(form.locator('[data-testid=kitchen-station-form-submit]')).toHaveText('Save');
    await form.locator('[data-testid=kitchen-station-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(row(page, `${BAR} 2`)).toContainText('No');
    const saved = await api<{ rows: { name: string; is_active: boolean }[] }>(context, A, 'GET', `/kitchen/stations?search=${encodeURIComponent(BAR)}&limit=10`);
    expect(saved.data.rows.map((station) => [station.name, station.is_active])).toEqual([[`${BAR} 2`, false]]);
  } finally {
    await context.close();
  }
});

test('KITCHEN-F04, F03: «Route» sends a product and a category to a station, «Remove» takes one away, and «Delete» waits until nothing is routed', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/stations', { width: 1440, height: 900 });
  try {
    const view = shown(page);
    const grill = await stationId(context, GRILL);
    await expect(row(page, GRILL)).toBeVisible();

    // KITCHEN-F04: the product by its name, from the station's own «Route».
    await rowAction(page, 'kitchen-stations', grill, 'route');
    const form = page.locator('ion-modal[data-testid=kitchen-route-form]');
    await expect(form).toBeVisible();
    await expect(form.locator('[data-testid=kitchen-route-form-station]')).toContainText(GRILL);
    await pick(page, 'kitchen-route-form-product', burger.sku, burger.name);
    await capture(page, 'KITCHEN-F04', async () => {
      await expect(form.locator('[data-testid=kitchen-route-form-submit]')).toBeInViewport();
    });
    await form.locator('[data-testid=kitchen-route-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(route(page, burger.name)).toContainText('Product');
    await expect(route(page, burger.name)).toContainText(GRILL);

    // The category, from the routing's own «Route».
    await view.locator('[data-testid=kitchen-routing-primary-action]').click();
    await choose(page, form.locator('[data-testid=kitchen-route-form-station]'), GRILL);
    await form.locator('[data-testid=kitchen-route-form-kind] ion-segment-button').filter({ hasText: 'Category' }).click();
    await pick(page, 'kitchen-route-form-category', CATEGORY, CATEGORY);
    await form.locator('[data-testid=kitchen-route-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(route(page, CATEGORY)).toContainText('Category');

    // KITCHEN-F03: with routes, «Delete» asks and then says why it cannot.
    await rowAction(page, 'kitchen-stations', grill, 'delete');
    const dialog = page.locator('ion-modal[data-testid=kitchen-stations-delete]');
    await expect(dialog).toContainText(`Delete «${GRILL}»?`);
    await capture(page, 'KITCHEN-F03', async () => {
      await expect(dialog.locator('[data-testid=kitchen-stations-delete-submit]')).toBeInViewport();
    });
    await dialog.locator('[data-testid=kitchen-stations-delete-submit]').click();
    await expect(dialog).toContainText('This station cannot be deleted');
    await dialog.locator('[data-testid=kitchen-stations-delete-cancel]').click();
    await expect(row(page, GRILL)).toBeVisible();

    // «Remove» on each route; then the station goes.
    await route(page, burger.name).locator('[data-testid$=-remove]').click();
    await expect(route(page, burger.name)).toHaveCount(0);
    await route(page, CATEGORY).locator('[data-testid$=-remove]').click();
    await expect(route(page, CATEGORY)).toHaveCount(0);
    await rowAction(page, 'kitchen-stations', grill, 'delete');
    await dialog.locator('[data-testid=kitchen-stations-delete-submit]').click();
    await expect(row(page, GRILL)).toHaveCount(0);
    // Its name is free again (KITCHEN-F01).
    expect((await api(context, A, 'POST', '/kitchen/stations', { name: GRILL })).status).toBe(201);
  } finally {
    await context.close();
  }
});

// flow: SALE-F20, KITCHEN-F05 — hub#1017: a waiter seats a table on the plan, opens its check with «Charge» and adds a
// dish. The till opens that check on «Check», and there, above the total and «Charge», «Send order (1)» is in view: on a
// tablet on its side (1280×800) and upright (800×1280, the check is the drawer), on «Current order» too, and again when
// the app is opened anew on that check (it starts on «Check»). A send from «Check» goes to the kitchen and the bar goes.
// In Spanish the bar says «Enviar comanda (1)». In Chrome with the real Tables, Sales, Kitchen and Inventory apps. What a
// run creates — its zone «E2E Tbs <stamp>», its table, the checks and their lines, their kitchen tickets and its
// product — is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, capture, login, psql, shown } from './helpers';
import { cleanInventory, type Product } from './inventory-helpers';
import { checkWithDish, cleanSales, dishForTheTill, openTillCart, restoreDrawer, stamp, zoneWithTable } from './sale-helpers';

const RUN = stamp();
const ZONE = `E2E Tbs ${RUN}`;
const TABLET = [
  { label: '1280', width: 1280, height: 800 },
  { label: '800', width: 800, height: 1280 },
];

let dish: Product;
let zoneId: string;
let tableId: string;

/** This spec's zones (any run's), their tables and their table checks with their moves, first (a table check names its
 *  check); then the sales, their kitchen tickets with them (`cleanSales`), and the products. */
function cleanUp(): void {
  const zones = "select id from table_zone where name like 'E2E Tbs %'";
  const tables = `select id from table_table where zone_id in (${zones})`;
  psql(
    [
      `create temp table e2e_tbsend_sessions as select session_id as id from table_sessionmove where table_id in (${tables}) union select id from table_tablesession where table_id in (${tables})`,
      'delete from table_sessionmove where session_id in (select id from e2e_tbsend_sessions)',
      `delete from table_hold where table_id in (${tables})`,
      'update table_tablesession set transferred_from_id = null, merged_into_id = null, split_from_id = null where id in (select id from e2e_tbsend_sessions)',
      'delete from table_tablesession where id in (select id from e2e_tbsend_sessions)',
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where id in (${zones})`,
    ].join('; '),
  );
  cleanSales();
  cleanInventory();
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  dish = await dishForTheTill(browser, 'TBSEND', RUN);
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/table/floor-plan');
  ({ zoneId, tableId } = await zoneWithTable(context, ZONE, RUN));
  await context.close();
});

test.afterAll(() => {
  try {
    cleanUp();
  } finally {
    restoreDrawer();
  }
});

const tab = (page: Page, which: 'check' | 'round') => shown(page).locator(`[data-testid=pos-cart-tab-${which}]`);

/** On `which` tab, «Send order (N)» (`words`) whole in view and above the foot: the total and «Charge». On a phone too
 *  low to keep it pinned (`scrolled`) it rides after the lines (SALE-F20, hub#787): scrolled to, it is the same. */
async function sendAboveTheFoot(page: Page, which: 'check' | 'round', words: string, where: string, scrolled = false): Promise<void> {
  await expect(tab(page, which), `«${which}» chosen ${where}`).toHaveAttribute('aria-selected', 'true');
  const send = shown(page).locator('[data-testid=pos-kitchen-send]');
  if (scrolled) await send.scrollIntoViewIfNeeded();
  await expect(send, `«Send order» ${where}`).toBeInViewport({ ratio: 1 });
  await expect(send).toContainText(words);
  const bar = await send.boundingBox();
  const total = await shown(page).locator('[data-testid=pos-total]').boundingBox();
  const charge = await shown(page).locator('[data-testid=pos-charge]').boundingBox();
  expect(bar && total && charge && bar.y + bar.height <= total.y && total.y <= charge.y, `«Send order» above the total and «Charge» ${where}`).toBe(true);
}

test('SALE-F20 (hub#1017): a table seated on the plan offers «Send order (1)» on «Check», on «Current order» and opened anew', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await login(page, A, '/table/floor-plan');
  const view = shown(page);
  await view.locator('[data-testid=table-floor-mode-service]').click();
  await view.locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();

  // Tables → the free table → seat two → its window → «Charge»: the till on the table's check.
  await view.locator(`[data-testid=table-floor-tile-${tableId}]`).click();
  await page.locator('[data-testid=table-guests-quick-2]').click();
  await expect(view.locator(`[data-testid=table-floor-tile-${tableId}]`)).toContainText('Occupied');
  await view.locator(`[data-testid=table-floor-tile-${tableId}]`).click();
  await page.locator('ion-modal[data-testid=table-sheet] [data-testid=table-sheet-action-charge]').click();
  await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(`Table ${RUN}`);

  // A dish: the check stays on «Check», the tab it opened on, and «Send order (1)» is there.
  await shown(page).locator(`[data-testid=pos-product-${dish.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-cart-tab-round-badge]')).toHaveText('1');
  for (const size of TABLET) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openTillCart(page);
    await sendAboveTheFoot(page, 'check', 'Send order (1)', `on «Check» at ${size.label}`);
    await capture(page, `APP-SALE-SALE-F20-check-${size.label}`);
    await tab(page, 'round').click();
    await sendAboveTheFoot(page, 'round', 'Send order (1)', `on «Current order» at ${size.label}`);
    await tab(page, 'check').click();
  }

  // The app opened anew on that check: it starts on «Check», «Send order (1)» in view.
  for (const size of TABLET) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.reload();
    await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
    await openTillCart(page);
    await expect(shown(page).locator('[data-testid=pos-cart-tab-round-badge]')).toHaveText('1');
    await sendAboveTheFoot(page, 'check', 'Send order (1)', `opened anew at ${size.label}`);
  }

  // Sent from «Check»: the kitchen has it, nothing waits and the bar goes; «Charge» is still there.
  await shown(page).locator('[data-testid=pos-kitchen-send]').click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Order 1 sent to the kitchen.' })).toBeVisible();
  await expect(shown(page).locator('[data-testid=pos-cart-tab-round-badge]')).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=pos-kitchen-send]')).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=pos-charge]')).toBeVisible();
});

test('SALE-F20 (hub#1017): in Spanish «Cuenta» offers «Enviar comanda (1)» above the total and «Cobrar»', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await checkWithDish(page, context, 'es', dish);
  await expect(tab(page, 'check')).toContainText('Cuenta');
  // The tablet both ways, and the fleet's tablet and low phone, where the check is the drawer.
  for (const size of [...TABLET, { label: '820', width: 820, height: 1180 }, { label: '375', width: 375, height: 667 }]) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openTillCart(page);
    await sendAboveTheFoot(page, 'check', 'Enviar comanda (1)', `in Spanish at ${size.label}`, size.label === '375');
    await capture(page, `APP-SALE-SALE-F20-check-es-${size.label}`);
  }
});

// flow: SALE-F01 SALE-F38 (apps/sale/WORKBOOK.md) — with Services on, «All», the chip the till opens on, shows the
// services with the articles and its count counts both: a haircut for a walk-in is a tap away, with no change of chip.
// The magnifier finds it by name too, without saying first that no product matches. Screenshots of the till in the
// three viewports. What this file creates is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, shown, turnOffTurnedOn, turnOnMissing } from './helpers';
import { drawerOff, linesOf, openTillCart, restoreDrawer, tillGrid, tillReady } from './sale-helpers';
import { cleanUp, FLOW_VIEWPORTS, named, post } from './service-helpers';

const turnedOn: string[] = [];

/** How many rows a list of the hub has (its first page of one row says the total). */
async function totalOf(context: Parameters<typeof api>[0], path: string): Promise<number> {
  const res = await api<{ total: number }>(context, A, 'GET', path);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(200);
  return res.data.total;
}

const allChip = (page: Page) => shown(page).locator('[data-testid=pos-category-all]');

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await turnOnMissing(context, A, ['service'], turnedOn);
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  cleanUp();
  restoreDrawer();
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/');
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

test('SALE-F38 (hub#2627): «All» shows the services with the articles, counts them and sells one', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const haircut = await post<{ id: string; name: string }>(context, '/service/services', {
    name: named('Corte'),
    price: 2500,
    tax_category_key: 'service.generic',
  });
  const articles = await totalOf(context, '/inventory/products?is_active=true&include_sold_out=true&limit=1&offset=0');
  const services = await totalOf(context, '/service/services/for_sale?limit=1&offset=0');

  await page.goto(`${A}/sale/pos`);
  await tillReady(page);
  await expect(allChip(page)).toHaveClass(/segment-button-checked/);
  const tile = tillGrid(page).locator(`[data-testid=pos-service-${haircut.id}]`);
  await expect(tile).toBeVisible();
  await expect(allChip(page)).toContainText(`${articles + services} items`);

  await tile.click();
  await expect(linesOf(page, haircut)).toHaveCount(1);

  for (const size of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(tile).toBeVisible();
    await capture(page, `SALE-ALL-SERVICES-${size.label}`);
  }
  await openTillCart(page);
  await expect(linesOf(page, haircut)).toHaveCount(1);
});

test('SALE-F38 (hub#2627): in «All», the magnifier finds a service by its name', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const haircut = await post<{ id: string; name: string }>(context, '/service/services', {
    name: named('Corte'),
    price: 2500,
    tax_category_key: 'service.generic',
  });
  await page.goto(`${A}/sale/pos`);
  await tillReady(page);
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  await shown(page).locator('[data-testid=pos-search] input').fill(haircut.name);
  await expect(shown(page).locator(`[data-testid=pos-search-service-${haircut.id}]`)).toBeVisible();
  await expect(shown(page).locator('[data-testid=pos-search-empty]')).toHaveCount(0);
});

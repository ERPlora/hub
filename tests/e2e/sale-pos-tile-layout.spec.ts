import { expect, test } from '@playwright/test';

import { A, capture, horizontalOverflow, login, shown, untilStill } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { stamp } from './sale-helpers';

const RUN = stamp();

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await createProduct(context, { name: `E2E Tile ${RUN}`, sku: `E2E-TILE-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => cleanInventory());

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`the catalogue tile stacks its photo above its text at ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await login(page, A, '/sale/pos');
    const tile = shown(page).locator('[data-testid^=pos-product-]').first();
    await tile.waitFor({ state: 'visible' });
    const layout = await tile.evaluate((el) => {
      const rect = (selector: string) => {
        const box = selector === ':scope' ? el.getBoundingClientRect() : el.querySelector(selector)?.getBoundingClientRect();
        return box ? { x: box.x, y: box.y, width: box.width, height: box.height, bottom: box.bottom } : undefined;
      };
      const native = el.shadowRoot?.querySelector('button');
      const inner = native?.querySelector('.button-inner');
      return {
        tile: rect(':scope'),
        thumb: rect('.pos-tile__thumb'),
        info: rect('.pos-tile__info'),
        nativeDisplay: native ? getComputedStyle(native).display : undefined,
        innerDisplay: inner ? getComputedStyle(inner).display : undefined,
        innerDirection: inner ? getComputedStyle(inner).flexDirection : undefined,
      };
    });
    console.log(JSON.stringify({ viewport, layout }));
    expect(layout.thumb).toBeDefined();
    expect(layout.info).toBeDefined();
    expect(layout.thumb!.bottom).toBeLessThanOrEqual(layout.info!.y + 1);
    expect(layout.thumb!.width).toBeCloseTo(layout.tile!.width - 2, 0);
    expect(layout.info!.width).toBeCloseTo(layout.tile!.width - 2, 0);
  });
}


for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`dark mode and the terracotta palette keep the shared surfaces usable at ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await login(page, A, '/sale/pos');
    for (const [name, path, ready] of [
      ['home', '/', '[data-testid=home-my-app]'],
      ['datatable', '/demo/items', '.data-table__row--data, .data-table__empty'],
      ['pos', '/sale/pos', '[data-testid^=pos-product-]'],
    ] as const) {
      await page.goto(`${A}${path}`);
      await page.evaluate(() => {
        document.documentElement.classList.add('ion-palette-dark');
        document.documentElement.setAttribute('data-ep-palette', 'terracotta');
      });
      await shown(page).locator(ready).first().waitFor({ state: 'visible' });
      await untilStill(page);
      expect(await horizontalOverflow(page), `${name} at ${viewport.width}: no sideways scroll`).toBeLessThanOrEqual(0);
      await capture(page, `poc-${name}-dark-terracotta-${viewport.width}`);
    }
  });
}


test('the mobile cart button grows around its total and keeps the count readable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid^=pos-product-]').first().click();
  const fab = shown(page).locator('[data-testid=pos-cart-fab]');
  await expect(fab).toBeVisible();
  await expect(fab.locator('[data-testid=pos-cart-fab-total]')).toContainText(/1[.,]50/);
  await expect(fab.locator('[data-testid=pos-cart-fab-count]')).toHaveText('1');
  const boxes = await fab.evaluate((el) => {
    const box = (selector: string) => {
      const rect = el.querySelector(selector)?.getBoundingClientRect();
      return rect ? { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom } : undefined;
    };
    const rect = el.getBoundingClientRect();
    const nativeRect = el.shadowRoot?.querySelector('button')?.getBoundingClientRect();
    const button = { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    const native = nativeRect ? { right: nativeRect.right } : undefined;
    return { button, native, total: box('[data-testid=pos-cart-fab-total]'), count: box('[data-testid=pos-cart-fab-count]') };
  });
  expect(boxes.total!.right).toBeLessThanOrEqual(boxes.button!.right - 8);
  expect(boxes.total!.right).toBeLessThanOrEqual(boxes.native!.right - 8);
  expect(boxes.count!.right).toBeLessThanOrEqual(boxes.button!.right + 8);
  expect(boxes.count!.bottom).toBeLessThanOrEqual(boxes.button!.top + 16);
  await capture(page, 'poc-fab-mobile');
});

// flow: INVENTORY-F03 — while the Products list scrolls under its sticky head, the head stays on top of what the rows
// hold: the «Active» switch of a row passing under «Status» never paints over that title (hub#2022). Ionic's
// ion-toggle brings its own z-index, the same as the head's, so the row's switch came out on top.
// Measured at the tablet's two orientations, where Products is a list with its head.
import { expect, type Locator, test } from '@playwright/test';

import { A, capture, hostPage, shown } from './helpers';
import { cleanInventory, createProduct, productsReady, stamp } from './inventory-helpers';

const RUN = stamp();
/** Enough products for the list to scroll inside its box at both orientations. */
const PRODUCTS = 24;
const TABLET = [
  { label: 'landscape', width: 1280, height: 800 },
  { label: 'portrait', width: 800, height: 1280 },
] as const;

test.beforeAll(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/inventory/products' });
  for (let i = 0; i < PRODUCTS; i++) {
    await createProduct(context, { name: `E2E Head ${RUN} ${String(i).padStart(2, '0')}`, sku: `E2E-HEAD-${RUN}-${i}` });
  }
  await context.close();
});

test.afterAll(cleanInventory);

/** Scrolls the list until the first switch sits right under the title of its column, then says what is painted
 *  at that title's centre: inside the head, or the row content on top of it. */
async function underItsTitle(table: Locator) {
  return table.evaluate((root) => {
    const toggle = root.querySelector('.data-table__row--data ion-toggle');
    const cell = toggle?.closest('[role=cell]');
    const column = cell ? [...(cell.parentElement?.querySelectorAll(':scope > [role=cell]') ?? [])].indexOf(cell) : -1;
    const title = root.querySelectorAll('.data-table__row--head > [role=columnheader]')[column];
    let box: Element | null = cell ?? null;
    while (box && !(box.scrollHeight > box.clientHeight && /auto|scroll/.test(getComputedStyle(box).overflowY))) box = box.parentElement;
    if (!toggle || !title || !box) return { ready: false, inHead: false, painted: '' };
    const at = title.getBoundingClientRect();
    const x = at.left + at.width / 2;
    const y = at.top + at.height / 2;
    const switchAt = toggle.getBoundingClientRect();
    box.scrollTop += switchAt.top + switchAt.height / 2 - y;
    const under = toggle.getBoundingClientRect();
    const hit = document.elementFromPoint(x, y);
    return {
      ready: under.top <= y && under.bottom >= y,
      inHead: !!hit?.closest('.data-table__row--head'),
      painted: hit ? `${hit.tagName.toLowerCase()}.${[...hit.classList].join('.')}` : '',
    };
  });
}

for (const vp of TABLET) {
  test(`ui:DataTable on a tablet in ${vp.label}: a row's switch never paints over the sticky head`, async ({ browser }) => {
    const owner = await hostPage(browser, A, { next: '/inventory/products', viewport: { width: vp.width, height: vp.height } });
    try {
      const page = owner.page;
      await productsReady(page);
      const table = shown(page).locator('.data-table').first();
      await expect(table.locator('.data-table__row--head')).toBeVisible();
      await expect(table.locator('.data-table__row--data ion-toggle').first()).toBeVisible();
      const seen = await underItsTitle(table);
      expect(seen.ready, 'a switch scrolled right under the title of its column').toBe(true);
      expect(seen.inHead, `the head shows at the centre of that title, not ${seen.painted}`).toBe(true);
      await capture(page, `FIX-UI-DATATABLE-HEAD-OVER-ROW-CONTROLS-${vp.label}`);
    } finally {
      await owner.context.close();
    }
  });
}

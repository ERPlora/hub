// FIX-DATATABLE evidence (ui mig/FIX-DATATABLE): a list page with AppPage `content-layout="fill"` and a
// DataTable `fill filterable` fills the space between the topbar and the tabbar at 390, 834 and 1440 px,
// with its footer fixed and its rows scrolling inside (on a phone the list grows with the page, #218);
// the funnel counts the filters in use; its panel pushes the list into two columns from 834 px and is a
// sheet strictly between the header and the tabbar below (outfitkit#75/#197).
import { type BrowserContext, type Page, expect, test } from '@playwright/test';

import { A, api, createItem, listReady, login, shot, shown } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

async function seed(context: BrowserContext, prefix: string, count: number): Promise<void> {
  for (let i = 1; i <= count; i += 1) await createItem(context, A, `${prefix} ${String(i).padStart(2, '0')}`);
}

async function cleanup(context: BrowserContext, prefix: string): Promise<void> {
  const found = await api<{ rows: { id: string }[] }>(context, A, 'GET', `/demo/items?limit=100&search=${encodeURIComponent(prefix)}`);
  for (const row of found.data.rows) await api(context, A, 'POST', '/demo/items/delete', { id: row.id });
}

/** Boxes of the visible page: its content area, its tabbar, the table, its footer, rows and panel. */
async function geometry(page: Page) {
  return page.evaluate(() => {
    const view = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden)') as HTMLElement;
    const box = (el: Element | null | undefined) => {
      const r = el?.getBoundingClientRect();
      return r ? { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width) } : null;
    };
    const content = view.querySelector('ion-content') as HTMLElement;
    const rows = view.querySelector('.data-table__scroll, .data-table__cards') as HTMLElement | null;
    return {
      content: box(content),
      tabbar: box(view.querySelector('ion-footer.section-tabbar')),
      table: box(view.querySelector('.data-table')),
      pager: box(view.querySelector('.data-table__pager')),
      drawer: box(view.querySelector('.data-table__drawer')),
      rowsScrollInside: rows ? rows.scrollHeight > rows.clientHeight + 1 : null,
      paddingBottom: parseFloat(getComputedStyle(content).getPropertyValue('--padding-bottom')) || 0,
    };
  });
}

test('FIX-DATATABLE: fill to the tabbar, funnel with count, panel in two columns ≥834 and a sheet below', async ({ page, context }) => {
  test.setTimeout(240_000);
  await login(page, A);
  const prefix = `FXDT${Date.now().toString(36)}`;
  await seed(context, prefix, 30);
  const results: Record<string, unknown> = {};
  try {
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/demo/items');
      await listReady(page);
      await page.waitForTimeout(500);
      const table = shown(page).locator('.data-table');

      // Filter by «Open» through the panel: the funnel then counts 1.
      const funnel = table.getByTestId('demo-items-filters-toggle');
      await funnel.click();
      const panel = table.getByTestId('demo-items-filters-panel');
      await expect(panel).toBeVisible();
      await panel.getByTestId('demo-items-filter-status').click();
      await page.locator('ion-popover.select-popover ion-radio').filter({ hasText: /^Open$/ }).click();
      await page.locator('ion-popover.select-popover').waitFor({ state: 'detached' });
      await panel.getByTestId('demo-items-filters-apply').click();
      await expect(panel).toBeHidden();
      await expect(table.getByTestId('demo-items-filters-count')).toHaveText('1');
      await listReady(page);
      await page.waitForTimeout(400);
      const closed = await geometry(page);
      await page.screenshot({ path: shot(`FIX-DATATABLE-${vp.label}-list`) });

      await funnel.click();
      await expect(panel).toBeVisible();
      await page.waitForTimeout(400);
      const open = await geometry(page);
      await page.screenshot({ path: shot(`FIX-DATATABLE-${vp.label}`) });
      results[vp.label] = { closed, open };

      const c = closed.content!;
      const tab = closed.tabbar!;
      expect(tab.top, 'the content ends where the tabbar begins').toBe(c.bottom);
      if (vp.width > 640) {
        // The table reaches the bottom of the content area (its padding apart); its footer is on screen.
        expect(Math.abs(closed.table!.bottom - (c.bottom - closed.paddingBottom)), JSON.stringify(closed)).toBeLessThanOrEqual(2);
        expect(closed.pager!.bottom).toBeLessThanOrEqual(c.bottom);
        expect(closed.rowsScrollInside, 'the rows scroll inside the table').toBe(true);
      } else {
        // A phone: the list grows with its rows from the page's height (one scroll, #218).
        expect(closed.table!.bottom).toBeGreaterThanOrEqual(c.bottom - closed.paddingBottom - 2);
      }
      const d = open.drawer!;
      if (vp.width >= 834) {
        // Two columns: the 360px panel at the table's right edge, as tall as the table.
        expect(d.width).toBe(360);
        expect(Math.abs(d.right - open.table!.right)).toBeLessThanOrEqual(1);
        expect(Math.abs(d.bottom - open.table!.bottom)).toBeLessThanOrEqual(1);
      } else {
        // A sheet strictly between the header and the tabbar (#197).
        expect(d.top).toBe(open.content!.top);
        expect(d.bottom).toBe(open.tabbar!.top);
        expect(d.width).toBe(vp.width);
      }
      await panel.getByTestId('demo-items-filters-clear').click();
      await expect(table.getByTestId('demo-items-filters-count')).toHaveCount(0);
      await panel.getByTestId('demo-items-filters-close').click();
      await expect(panel).toBeHidden();
    }
  } finally {
    console.log(JSON.stringify(results));
    await cleanup(context, prefix);
  }
});

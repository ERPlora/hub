// FIX-DATATABLE-HUB evidence (ui 070e74f): a list page with AppPage `content-layout="fill"` and a
// DataTable `fill` fills its page down to its bottom edge — the section tabbar when the page has one
// (Customers), the bottom of its content area when it has none (the demo) — at 390, 834 and 1440 px, with
// its footer fixed and its rows scrolling inside, one scroll only (on a phone the list grows with the page
// and only the page scrolls, #218);
// the demo's funnel (`filterable`) counts the filters in use; its panel pushes the list into two columns
// from 834 px and is a sheet strictly between the header and that bottom edge (outfitkit#75/#197).
import { type BrowserContext, type Page, expect, test } from '@playwright/test';

import { cleanUp, createCard, customersReady, e2eName, searchList, spanishMobile } from './customer-helpers';
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
  return page.evaluate(async () => {
    const view = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden)') as HTMLElement;
    const box = (el: Element | null | undefined) => {
      const r = el?.getBoundingClientRect();
      return r ? { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width) } : null;
    };
    const content = view.querySelector('ion-content') as HTMLElement;
    const rows = view.querySelector('.data-table__scroll, .data-table__cards') as HTMLElement | null;
    const scroller = await (content as HTMLElement & { getScrollElement(): Promise<HTMLElement> }).getScrollElement();
    return {
      content: box(content),
      tabbar: box(view.querySelector('ion-footer.section-tabbar')),
      table: box(view.querySelector('.data-table')),
      pager: box(view.querySelector('.data-table__pager')),
      drawer: box(view.querySelector('.data-table__drawer')),
      rowsScrollInside: rows ? rows.scrollHeight > rows.clientHeight + 1 : null,
      pageScrolls: scroller.scrollHeight > scroller.clientHeight + 1,
      paddingBottom: parseFloat(getComputedStyle(content).getPropertyValue('--padding-bottom')) || 0,
      windowHeight: window.innerHeight,
    };
  });
}

type Geometry = Awaited<ReturnType<typeof geometry>>;

/** Where the list ends: the top of the section tabbar when the page has one, else the bottom of its content area. */
function bottomEdge(g: Geometry): number {
  return g.tabbar?.top ?? g.content!.bottom;
}

/** The list fills its page down to `bottomEdge` with one scroll only: on a desk the rows scroll inside the
 *  table and its footer stays on screen; on a phone the list grows with its rows and only the page scrolls (#218). */
function expectFills(g: Geometry, width: number): void {
  const c = g.content!;
  const edge = bottomEdge(g);
  if (g.tabbar) expect(g.tabbar.top, 'the content ends where the tabbar begins').toBe(c.bottom);
  else expect(c.bottom, 'without a tabbar the content reaches the bottom of the window').toBe(g.windowHeight);
  if (width > 640) {
    // The table reaches the bottom edge (the content's padding apart); its footer is on screen.
    expect(Math.abs(g.table!.bottom - (edge - g.paddingBottom)), JSON.stringify(g)).toBeLessThanOrEqual(2);
    expect(g.pager!.bottom).toBeLessThanOrEqual(edge);
    expect(g.rowsScrollInside, 'the rows scroll inside the table').toBe(true);
    expect(g.pageScrolls, 'no double scroll: the page itself does not scroll').toBe(false);
  } else {
    expect(g.table!.bottom).toBeGreaterThanOrEqual(edge - g.paddingBottom - 2);
    expect(g.rowsScrollInside, 'no double scroll: the rows do not scroll inside the table').toBe(false);
    expect(g.pageScrolls, 'the page scrolls the grown list').toBe(true);
  }
}

test('FIX-DATATABLE-HUB: the demo (no tabs) fills to the bottom of its content, funnel with count, panel in two columns ≥834 and a sheet below', async ({ page, context }) => {
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
      await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-${vp.label}-list`) });

      await funnel.click();
      await expect(panel).toBeVisible();
      await page.waitForTimeout(400);
      const open = await geometry(page);
      await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-${vp.label}`) });
      results[vp.label] = { closed, open };

      expect(closed.tabbar, 'the demo has no section tabs').toBeNull();
      expectFills(closed, vp.width);
      const d = open.drawer!;
      if (vp.width >= 834) {
        // Two columns: the 360px panel at the table's right edge, as tall as the table.
        expect(d.width).toBe(360);
        expect(Math.abs(d.right - open.table!.right)).toBeLessThanOrEqual(1);
        expect(Math.abs(d.bottom - open.table!.bottom)).toBeLessThanOrEqual(1);
      } else {
        // A sheet strictly between the header and the bottom edge (#197).
        expect(d.top).toBe(open.content!.top);
        expect(d.bottom).toBe(bottomEdge(open));
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

test('FIX-DATATABLE-HUB: a list with section tabs (Customers) fills down to its tabbar, one scroll only', async ({ page, context }) => {
  test.setTimeout(240_000);
  await login(page, A, '/customer/customers');
  const stamp = `FXDT${Date.now().toString(36)}`;
  for (let i = 1; i <= 30; i += 1) {
    await createCard(context, { name: e2eName(`${stamp} ${String(i).padStart(2, '0')}`), phone: spanishMobile() });
  }
  const results: Record<string, unknown> = {};
  try {
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/customer/customers');
      await customersReady(page);
      await searchList(page, 'customer-list', stamp);
      const rows = shown(page).locator('[data-testid=customer-list-row]');
      await expect(rows.first()).toContainText(stamp);
      await expect(rows.filter({ hasNotText: stamp })).toHaveCount(0);
      await page.waitForTimeout(400);
      const closed = await geometry(page);
      await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-customers-${vp.label}`) });
      results[vp.label] = closed;
      expect(closed.tabbar, 'Customers has its section tabbar').not.toBeNull();
      expectFills(closed, vp.width);
    }
  } finally {
    console.log(JSON.stringify(results));
    cleanUp();
  }
});

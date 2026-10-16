// FIX-DATATABLE-HUB evidence (ui 070e74f): a list page with AppPage `content-layout="fill"` and a
// DataTable `fill` fills its page down to its bottom edge — the section tabbar when the page has one
// (Customers), the bottom of its content area when it has none (the demo) — at 390, 834 and 1440 px, with
// its footer fixed and its rows scrolling inside, one scroll only (on a phone the list grows with the page
// and only the page scrolls, #218);
// the demo's funnel (`filterable`) counts the filters in use; its panel pushes the list into two columns
// from 834 px and is a sheet strictly between the header and that bottom edge (outfitkit#75/#197).
// flow: ui:DataTable — FIX-UI-DATATABLE-CLIP: nothing of the table is cut off — a date range fits its
// 360px panel (both ends whole, outline included) and a card title wraps instead of ending in «…».
import { type BrowserContext, type Locator, type Page, expect, test } from '@playwright/test';

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

/** How far a date range in the open filter panel reaches past the panel's content box, in px (0 = it
 *  fits): every box of both ends counts, the outline of «To» included; and whether the panel's body
 *  scrolls sideways. */
async function rangeOverflow(panel: Locator, ends: [string, string]) {
  return panel.evaluate((el, testIds) => {
    const body = el.querySelector('.data-table__drawer-body') as HTMLElement;
    const r = body.getBoundingClientRect();
    const style = getComputedStyle(body);
    const left = r.left + parseFloat(style.paddingLeft);
    const right = r.right - parseFloat(style.paddingRight);
    let past = 0;
    for (const id of testIds) {
      const end = el.querySelector(`[data-testid="${id}"]`) as HTMLElement;
      for (const box of [end, ...end.querySelectorAll<HTMLElement>('*')]) {
        const b = box.getBoundingClientRect();
        if (!b.width) continue;
        past = Math.max(past, b.right - right, left - b.left);
      }
    }
    return { past: Math.round(past * 10) / 10, scrollsSideways: body.scrollWidth > body.clientWidth };
  }, ends);
}

const RANGE_PAGES = [
  { path: '/staff/members', table: 'staff-members', ends: ['hire_date_from', 'hire_date_to'] as [string, string] },
  { path: '/schedule/special-days', table: 'schedule-special-days', ends: ['date_from', 'date_to'] as [string, string] },
];

test('FIX-UI-DATATABLE-CLIP: a date range fits the 360px filter panel at 1440 and 834 (Staff «Hire date», Special days «Date»)', async ({ page }) => {
  test.setTimeout(180_000);
  await login(page, A, RANGE_PAGES[0].path);
  const results: Record<string, unknown> = {};
  for (const vp of VIEWPORTS.filter((v) => v.width >= 834)) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    for (const target of RANGE_PAGES) {
      await page.goto(`${A}${target.path}`);
      const view = shown(page);
      await view.locator(`[data-testid=${target.table}-row], [data-testid=${target.table}-empty]`).first().waitFor({ state: 'visible' });
      await view.locator(`[data-testid=${target.table}-filters-toggle]`).click();
      const panel = view.locator(`[data-testid=${target.table}-filters-panel]`);
      await expect(panel).toBeVisible();
      const ends = target.ends.map((name) => `${target.table}-filter-${name}`) as [string, string];
      for (const id of ends) await expect(panel.locator(`[data-testid=${id}] input[type=date]`)).toBeVisible();
      await page.waitForTimeout(400);
      const measured = await rangeOverflow(panel, ends);
      results[`${target.table}-${vp.label}`] = measured;
      if (target.table === 'staff-members') await page.screenshot({ path: shot(`FIX-UI-DATATABLE-CLIP-drawer-${vp.label}`) });
      expect(measured.past, `${target.path} at ${vp.label}: the range reaches past the panel`).toBeLessThanOrEqual(0.5);
      expect(measured.scrollsSideways, `${target.path} at ${vp.label}: the panel scrolls sideways`).toBe(false);
      await panel.locator(`[data-testid=${target.table}-filters-close]`).click();
      await expect(panel).toBeHidden();
    }
  }
  console.log(JSON.stringify(results));
});

/** Card titles on screen that cut their text (a «…» on one line, or more lines than their box shows). */
async function cutTitles(page: Page) {
  return shown(page)
    .locator('.data-table__card-title')
    .evaluateAll((titles) =>
      titles
        .filter((t) => t.getClientRects().length > 0)
        .map((t) => ({ text: (t.textContent ?? '').trim(), sw: t.scrollWidth, cw: t.clientWidth, sh: t.scrollHeight, ch: t.clientHeight }))
        .filter((t) => t.sw > t.cw || t.sh > t.ch),
    );
}

const CARD_VIEWPORTS = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
];

test('FIX-UI-DATATABLE-CLIP: card titles wrap whole at 375 and 820, never «…» on one line (Taxes → Categories, Rules)', async ({ page }) => {
  test.setTimeout(180_000);
  await login(page, A, '/tax/categories');
  const results: Record<string, unknown> = {};
  for (const vp of CARD_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    for (const [path, table] of [['/tax/categories', 'tax-categories'], ['/tax/rules', 'tax-rules']]) {
      await page.goto(`${A}${path}`);
      const view = shown(page);
      await view.locator('.data-table__cards, .data-table__row--data').first().waitFor({ state: 'visible' });
      // A tablet may show the list: the person picks «View as cards» (the cards are what a tablet clipped).
      if (!(await view.locator('.data-table__cards').isVisible())) await view.locator(`[data-testid=${table}-view-cards]`).click();
      const cards = view.locator('.data-table__cards');
      await expect(cards).toBeVisible();
      await expect(cards.locator('.data-table__card-title').first()).toBeVisible();
      await page.waitForTimeout(400);
      const cut = await cutTitles(page);
      results[`${path}-${vp.label}`] = { titles: await cards.locator('.data-table__card-title').count(), cut };
      if (path === '/tax/categories') await page.screenshot({ path: shot(`FIX-UI-DATATABLE-CLIP-cards-${vp.label}`) });
      expect(cut, `${path} at ${vp.label}: card titles cut`).toEqual([]);
    }
  }
  console.log(JSON.stringify(results));
});

// «Activity» on the Home (BASE-F09) against the real Sales: a sale charged through its API shows up live in
// the table at `/#actividad` with its number, amount in euros and status, and its date and time are read whole
// in the three viewports (hub#2637: at about 820 px the old hub's «Date» column cut the time off). Whole for the
// widest date the format can print, not only for this sale's: «Oct 22, 2026, 10:09 PM» was cut at 834 while
// «9:30 PM» fit, so a check of the clock's own time passed or failed by the hour it ran (2026-10-22).
// flow: BASE-F09
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, exposeMovingInPage, horizontalOverflow, login, shot, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, stamp } from './sale-helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const RUN = stamp();
let coffee: Product;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/');
  coffee = await createProduct(context, { name: `E2E Home coffee ${RUN}`, sku: `E2E-HOME-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
});

/** What cuts `el`'s text: the boxes that clip it, up to its table cell (or card field). Empty = whole. */
function cuts(el: Locator): Promise<string[]> {
  return el.evaluate((node) => {
    const range = document.createRange();
    range.selectNodeContents(node);
    const text = range.getBoundingClientRect();
    const found: string[] = [];
    const cell = node.closest('.data-table__cell, .data-table__field-value') ?? node;
    for (let at: Element | null = node as Element; at; at = at.parentElement) {
      const style = getComputedStyle(at);
      const box = at.getBoundingClientRect();
      const clips = style.overflowX !== 'visible' || style.overflowY !== 'visible' || at === cell;
      if (clips && (text.left < box.left - 0.5 || text.right > box.right + 0.5)) {
        found.push(`text ${Math.round(text.left)}–${Math.round(text.right)} cut by ${at.tagName.toLowerCase()} ${Math.round(box.left)}–${Math.round(box.right)}`);
      }
      if (at === cell) break;
    }
    return found;
  });
}

/**
 * The widest text `formatDateTime` (@erplora/ui: medium date + short time, «Oct 22, 2026, 10:09 PM») can print, in
 * the hub's two languages and `cell`'s own font, against the room inside `cell`. Dates and times are measured apart
 * (every day of a leap year at one time, every minute at one date) and the widest of each, then put together.
 */
function widestDate(cell: Locator): Promise<{ text: string; width: number; room: number }> {
  return cell.evaluate((node) => {
    const probe = document.createElement('span');
    probe.style.cssText = 'position: absolute; visibility: hidden; white-space: nowrap; left: 0; top: 0;';
    node.appendChild(probe);
    const width = (text: string) => {
      probe.textContent = text;
      return probe.getBoundingClientRect().width;
    };
    const widestOf = (format: Intl.DateTimeFormat, instants: Date[]) =>
      instants.reduce((best, at) => (width(format.format(at)) > width(format.format(best)) ? at : best));
    let found = { text: '', width: 0 };
    for (const locale of ['en', 'es']) {
      const format = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' });
      const days = Array.from({ length: 366 }, (_, day) => new Date(Date.UTC(2028, 0, 1 + day, 12, 0)));
      const minutes = Array.from({ length: 24 * 60 }, (_, minute) => new Date(Date.UTC(2028, 0, 1, 0, minute)));
      const day = widestOf(format, days);
      const time = widestOf(format, minutes);
      const text = format.format(new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), time.getUTCHours(), time.getUTCMinutes())));
      if (width(text) > found.width) found = { text, width: width(text) };
    }
    probe.remove();
    const style = getComputedStyle(node);
    const room = node.getBoundingClientRect().width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    return { ...found, room };
  });
}

type Box = { name: string; left: number; right: number; top: number; bottom: number };
type Toolbar = { bar: Box; controls: Box[]; settled: boolean };
type Size = { width: number; height: number };

/**
 * The toolbar row of «Activity» and each control painted in it (`display: none` ones left out), read once the page has
 * settled at `size`. Armed in the page BEFORE the resize (a `goto` to the same `/#actividad` reloads nothing: a read
 * right after `setViewportSize` raced the page answering the new size, and at 820 coming from 1440 it read the bar
 * still beside the side menu, 516 px wide, list/cards on a second line). From the `resize` on, each frame, until:
 *   - the shell answered the size: `ion-split-pane` shows or hides the side menu a frame AFTER the window changes,
 *     by its `when` (`lg` = 992 px, Ionic's breakpoints);
 *   - nothing animates (the list/cards switch slides its indicator), in the document or in a shadow root;
 *   - the bar holds still: the same boxes two frames in a row.
 * Never a fixed wait; `settled` is false when 600 frames go by without that.
 */
async function toolbarAt(page: Page, size: Size): Promise<Toolbar> {
  await exposeMovingInPage(page);
  await page.evaluate((target) => {
    const read = () => {
      const row = [...document.querySelectorAll('.data-table__bar-main')].find((el) =>
        el.querySelector('[data-testid=home-activity-search]'),
      );
      if (!row) return undefined;
      const box = (el: Element, name: string) => {
        const r = el.getBoundingClientRect();
        return { name, left: r.left, right: r.right, top: r.top, bottom: r.bottom };
      };
      const style = getComputedStyle(row);
      const inner = row.getBoundingClientRect();
      const controls = [...row.children]
        .filter((el) => getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().width > 0)
        .map((el) => box(el, el.getAttribute('data-testid') ?? el.className.toString().split(' ')[0]));
      const bar = {
        name: 'bar',
        left: inner.left + parseFloat(style.paddingLeft),
        right: inner.right - parseFloat(style.paddingRight),
        top: inner.top,
        bottom: inner.bottom,
      };
      return { bar, controls };
    };
    const breakpoints: Record<string, string> = {
      xs: '(min-width: 0px)',
      sm: '(min-width: 576px)',
      md: '(min-width: 768px)',
      lg: '(min-width: 992px)',
      xl: '(min-width: 1200px)',
    };
    const shellAnswered = () => {
      const pane = document.querySelector('ion-split-pane') as (Element & { when?: unknown }) | null;
      if (!pane || typeof pane.when !== 'string') return true;
      return pane.classList.contains('split-pane-visible') === matchMedia(breakpoints[pane.when] ?? pane.when).matches;
    };
    // helpers.ts's `movingInPage`, put in the page by `exposeMovingInPage`: the one detector of the e2e.
    const animating = () => (window as unknown as { __movingInPage: () => string[] }).__movingInPage().length > 0;
    (window as unknown as { __toolbar: Promise<unknown> }).__toolbar = new Promise((resolve) => {
      let last: string | undefined;
      let frames = 0;
      const frame = () => {
        const now = read();
        const seen = now && JSON.stringify(now);
        if (now && seen === last && shellAnswered() && !animating()) return resolve({ ...now, settled: true });
        last = seen;
        frames += 1;
        if (frames > 600) return resolve({ bar: now?.bar, controls: now?.controls ?? [], settled: false });
        requestAnimationFrame(frame);
      };
      const onResize = () => {
        if (innerWidth !== target) return;
        removeEventListener('resize', onResize);
        frame();
      };
      addEventListener('resize', onResize);
    });
  }, size.width);
  await page.setViewportSize(size);
  return page.evaluate(() => (window as unknown as { __toolbar: Promise<Toolbar> }).__toolbar);
}

async function rowOf(page: Page, id: string): Promise<Locator> {
  const row = shown(page).locator(`[data-testid=home-activity-row][data-id="${id}"]`);
  await expect(row).toBeVisible();
  return row;
}

test('BASE-F09 — the address `/#actividad` opens «Activity» on a full load too (a link, a bookmark, a reload)', async ({ page }) => {
  await login(page, A, '/');
  await page.goto('about:blank');
  await page.goto(`${A}/#actividad`);
  await expect(shown(page).locator('[data-testid="tab-activity"]')).toHaveClass(/segment-button-checked/);
  await expect(shown(page).locator('[data-testid=home-activity-search]')).toBeVisible();
  await page.reload();
  await expect(shown(page).locator('[data-testid="tab-activity"]')).toHaveClass(/segment-button-checked/);
  await expect(page).toHaveURL(`${A}/#actividad`);
});

test('BASE-F09 — a sale shows up live in «Activity», its date and time whole at 390, 834 and 1440', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/');
  await page.goto(`${A}/#actividad`);
  await expect(shown(page).locator('[data-testid=home-activity-search]')).toBeVisible();

  // Charged elsewhere (the API, as another till would): the open table gets it without a reload.
  const sale = await chargeByApi(context, { lines: [{ product: coffee.sku }], payments: [{ method: 'card' }] });
  const row = await rowOf(page, sale.id);
  await expect(row).toContainText(sale.number);
  await expect(row).toContainText(/1[.,]50/);

  for (const vp of [VIEWPORTS[1], VIEWPORTS[0], VIEWPORTS[2]]) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/#actividad`);
    const seen = await rowOf(page, sale.id);
    const cells = seen.locator('.data-table__cell, .data-table__field-value');
    const date = cells.first();
    // The date carries its time («22/10/2026, 9:30»), and nothing clips it, nor any other value of the row.
    await expect(date).toHaveText(/\d{1,2}:\d{2}/);
    await expect.poll(() => cuts(date), `date at ${vp.label}`).toEqual([]);
    for (const cell of await cells.all()) {
      expect(await cuts(cell), `«${await cell.innerText()}» at ${vp.label}`).toEqual([]);
    }
    // Nor would the widest date the format prints, whatever the hour of this run: a table cell keeps its value on one
    // line and ends it in «…»; a card's value wraps between words, so it never needs the widest on one line.
    if (await date.evaluate((node) => node.matches('.data-table__cell'))) {
      const widest = await widestDate(date);
      expect(widest.width, `«${widest.text}» in ${widest.room.toFixed(1)} px at ${vp.label}`).toBeLessThanOrEqual(widest.room + 0.5);
    }
    const overflow = await horizontalOverflow(page);
    expect(overflow, `no sideways scroll at ${vp.label}`).toBeLessThanOrEqual(0);
    // The list/cards switch slides its indicator when the width changes the view: capture it settled.
    await untilStill(page);
    await page.screenshot({ path: shot(`APP-BASE-1-BASE-F09-sale-${vp.label}`) });
  }
});

/** The fleet's tablet (820) beside the old hub's reference sizes. */
const TOOLBAR_VIEWPORTS = [...VIEWPORTS, { label: '820', width: 820, height: 1180 }];

test('BASE-F09 — the toolbar of «Activity» is one row from 820 to 1440, as in the old hub, and spills nowhere', async ({ page }) => {
  await login(page, A, '/');
  await page.goto(`${A}/#actividad`);
  await expect(shown(page).locator('[data-testid=home-activity-filters-toggle]')).toBeVisible();
  for (const vp of TOOLBAR_VIEWPORTS) {
    const { bar, controls, settled } = await toolbarAt(page, vp);
    expect(settled, `the page settled at ${vp.label}`).toBe(true);
    for (const control of controls) {
      expect(control.left, `${control.name} inside the bar at ${vp.label}`).toBeGreaterThanOrEqual(bar.left - 0.5);
      expect(control.right, `${control.name} inside the bar at ${vp.label}`).toBeLessThanOrEqual(bar.right + 0.5);
    }
    if (vp.label === '390') continue; // On a phone the search takes its own line (the old hub's too).
    // docs/reference/old-hub/dashboard-activity-834.png: search, columns, rows per page, list/cards and the
    // funnel on one line. Every control shares the search's line.
    const search = controls.find((c) => c.name === 'data-table__search');
    expect(search, `the search at ${vp.label}`).toBeDefined();
    for (const control of controls) {
      expect(control.top, `${control.name} on the search's line at ${vp.label}`).toBeLessThan(search!.bottom);
    }
  }
});

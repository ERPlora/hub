// flow: KITCHEN-F10 — Kitchen → Display with more tickets than fit, in Chrome: while the board scrolls, its bar of views
// stays whole at the very top of the content and no ticket shows above it nor through it, on a phone, a tablet upright and
// lying down and a desktop, and alone on the screen («Full screen»). The scrolled board is captured in 375×667,
// 820×1180 and 1440×900 (`kitchen-display-scrolled-<size>`). What a run creates — the tickets «e2e kbb <run> <n>» — is
// deleted after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, psql, saveSessionForTheSweep, shown } from './helpers';
import { stamp } from './sale-helpers';
import { ownerPage } from './service-helpers';

const RUN = stamp();
const LABEL = `e2e kbb ${RUN}`;
const TICKETS = 20;
const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1180', width: 1180, height: 820 },
  { label: '1440', width: 1440, height: 900 },
];
const CAPTURED = new Set(['375', '820', '1440']);

function cleanRun(): void {
  const tickets = "select id from kitchen_ticket where label like 'e2e kbb %'";
  psql(
    [
      `delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (${tickets}))`,
      `delete from kitchen_logentry where ticket_id in (${tickets})`,
      `delete from kitchen_ticketitem where ticket_id in (${tickets})`,
      `delete from kitchen_ticket where id in (${tickets})`,
    ].join('; '),
  );
}

async function openTickets(context: BrowserContext): Promise<void> {
  for (let n = 1; n <= TICKETS; n++) {
    const items = [{ name: 'Lentil soup' }, { name: 'Grilled steak' }, { name: 'Caesar salad' }];
    const res = await api(context, A, 'POST', '/kitchen/tickets', { label: `${LABEL} ${n}`, items });
    expect(res.status, JSON.stringify(res.data)).toBe(201);
  }
}

interface Strip {
  /** How far the box scrolled, to tell a board that never scrolled from one that hides nothing. */
  scrolled: number;
  /** The tickets with a point between the top of the scrolling box and the bottom of the bar, and the deepest such
   *  point from the top of the box. */
  tickets: number;
  deepest: number;
  /** How much of the bar's first row is hidden above the top of the box. */
  cut: number;
}

/**
 * Scrolls the board to `y` and measures what shows between the top of its scrolling box and the bottom of the bar: the
 * page's content, or the display itself once alone on the screen. The rounded corners of the content are left out.
 */
async function stripAt(page: Page, y: number): Promise<Strip> {
  return page.evaluate(async (top) => {
    const root = Array.from(document.querySelectorAll<HTMLElement>('[data-testid=kitchen-display]')).at(-1);
    const bar = root?.querySelector<HTMLElement>('.ep-order-board-bar');
    const row = bar?.querySelector<HTMLElement>('.ep-order-board-bar__main');
    if (!root || !bar || !row) throw new Error('kitchen display or its bar not found');
    const content = root.closest('ion-content') as (HTMLElement & { getScrollElement(): Promise<HTMLElement> }) | null;
    const box = document.fullscreenElement === root ? root : await content?.getScrollElement();
    if (!box) throw new Error('scrolling box not found');
    box.scrollTop = top;
    await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
    const edges = box.getBoundingClientRect();
    const below = bar.getBoundingClientRect().bottom;
    const tickets = new Set<Element>();
    let deepest = 0;
    for (let line = edges.top + 1; line < below - 1; line += 2) {
      for (let x = edges.left + 28; x < edges.right - 28; x += 16) {
        const ticket = document.elementFromPoint(x, line)?.closest('[data-testid^=kitchen-card-]');
        if (!ticket) continue;
        tickets.add(ticket);
        deepest = Math.max(deepest, Math.round(line - edges.top));
      }
    }
    const cut = Math.max(0, Math.round(edges.top - row.getBoundingClientRect().top));
    return { scrolled: box.scrollTop, tickets: tickets.size, deepest, cut };
  }, y);
}

/** What goes wrong at the top of the board while it scrolls 30 px at a time, up to 450 px or its end: tickets that
 *  show above the bar or through it, and the bar's tabs cut at the top. */
async function overBar(page: Page, where: string): Promise<string[]> {
  const wrong: string[] = [];
  let scrolled = 0;
  for (let y = 30; y <= 450 && scrolled === y - 30; y += 30) {
    const strip = await stripAt(page, y);
    scrolled = strip.scrolled;
    if (strip.tickets) wrong.push(`${where} at ${scrolled}px: ${strip.tickets} tickets show in the top ${strip.deepest}px`);
    if (strip.cut) wrong.push(`${where} at ${scrolled}px: the tabs are cut ${strip.cut}px at the top`);
  }
  expect(scrolled, `${where}: the board scrolls past its bar`).toBeGreaterThanOrEqual(90);
  return wrong;
}

test.beforeAll(cleanRun);
test.afterAll(cleanRun);

test('KITCHEN-F10: no ticket shows above the bar of views nor through it while the board scrolls', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/display', { width: 1440, height: 900 });
  try {
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    await openTickets(context);
    await saveSessionForTheSweep(context);
    await page.reload();
    const view = shown(page);
    await expect.poll(() => view.locator('[data-testid^=kitchen-card-]').count()).toBeGreaterThanOrEqual(TICKETS);

    const wrong: string[] = [];
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      wrong.push(...(await overBar(page, size.label)));
      if (CAPTURED.has(size.label)) await capture(page, `kitchen-display-scrolled-${size.label}`);
    }

    await page.setViewportSize({ width: 1440, height: 900 });
    await view.locator('[data-testid=kitchen-display-fullscreen]').click();
    await expect(view.locator('[data-testid=kitchen-display]')).toHaveClass(/kds--fullscreen/);
    wrong.push(...(await overBar(page, 'full screen')));
    await view.locator('[data-testid=kitchen-display-fullscreen]').click();

    expect(wrong).toEqual([]);
  } finally {
    await context.close();
  }
});

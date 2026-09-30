// Regression test for ERPlora/hub#2413 — on a phone, the blocking strip («You cannot issue invoices
// yet») pushed every full-height list down and its end went under the tabbar.
//
// The shell's work surfaces (a module's outlet, Staff, Apps…) are pinned to the scroller's height
// with a FLOOR under it (`--ok-work-surface-min`, hub#1745): on a short screen the surface overflows
// on purpose and the shell scrolls. The floor was sized against the box the viewport leaves, but the
// strip sits between the topbar and the scroller, so it eats that box too. On a 375×667 phone the
// box went from 535 px to 402 px — under the 480 px floor — and the floor switched on because of the
// warning alone: the table's footer («1 record», the pager, «Retry») ended up under the tabbar.
//
// The contract: the strip never decides whether a surface overflows. Where the floor was inert
// without the strip, the list still ends right above the tabbar with it; where the floor bites
// (a tablet on its side, hub#1745), it still bites — by exactly as much as without the strip, even
// when the strip grows because somebody opened what is missing.
//
// This bench boots a hub with no business identity, so the strip is up on every screen but Home.
import { test, expect, type Page } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';
import { VIEWPORTS } from './viewports';

test.use({ locale: 'es-ES' });

/** The phone of the report (the UI contract's «low phone») plus the three contract viewports. */
const FITTING = [{ width: 375, height: 667 }, ...VIEWPORTS] as const;

/** The tablet on its side of hub#1745: 268 px of box with a tabbar, well under the floor. */
const SHORT_LANDSCAPE = { width: 952, height: 426 } as const;

/** The work-surface floor, read from the theme's `:root` (the single source of the number). */
async function rootFloorPx(page: Page): Promise<number> {
  return page.evaluate(() =>
    parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ok-work-surface-min')),
  );
}

async function openStaff(page: Page, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await loggedInSession(page);
  await page.goto('/employees');
  await expect(page.getByTestId('setup-strip')).toBeVisible();
  await expect(page.getByTestId('employees-table')).toBeVisible();
}

/** Geometry of the visible Staff screen: the strip, the surface, the scroller and the tabbar. */
async function layout(page: Page) {
  return page.evaluate(() => {
    const table = document.querySelector<HTMLElement>('[data-testid="employees-table"]');
    const pageEl = table?.closest<HTMLElement>('.ion-page');
    const content = pageEl?.querySelector<HTMLElement>(':scope > ion-content');
    const scroller = content?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');
    const surface = table?.closest<HTMLElement>('.fill');
    const footer = pageEl?.querySelector<HTMLElement>(':scope > ion-footer');
    const strip = pageEl?.querySelector<HTMLElement>('[data-testid="setup-strip"]');
    if (!table || !content || !scroller || !surface || !footer || !strip) throw new Error('screen not laid out');
    return {
      strip: strip.getBoundingClientRect().height,
      surface: surface.getBoundingClientRect().height,
      tableBottom: table.getBoundingClientRect().bottom,
      tabbarTop: footer.getBoundingClientRect().top,
      overflow: scroller.scrollHeight - scroller.clientHeight,
    };
  });
}

test.describe('Blocking strip and full-height lists (hub#2413)', () => {
  for (const viewport of FITTING) {
    test(`${viewport.width}×${viewport.height}: the list ends above the tabbar under the strip, with nothing to scroll`, async ({
      page,
    }) => {
      await openStaff(page, viewport);
      await expect
        .poll(async () => {
          const l = await layout(page);
          return { endsAboveTabbar: l.tableBottom <= l.tabbarTop + 0.5, overflow: l.overflow };
        })
        .toEqual({ endsAboveTabbar: true, overflow: 0 });
    });
  }

  test(`${SHORT_LANDSCAPE.width}×${SHORT_LANDSCAPE.height}: the floor still bites under the strip, net of the strip`, async ({
    page,
  }) => {
    await openStaff(page, SHORT_LANDSCAPE);
    const floor = await rootFloorPx(page);
    expect(floor).toBeGreaterThan(0);

    // Folded strip (one row): the surface keeps the floor minus what the strip took, so the shell
    // still scrolls by exactly what it scrolled without the strip (hub#1745 stays fixed).
    await expect
      .poll(async () => {
        const l = await layout(page);
        return Math.abs(l.surface - (floor - l.strip)) <= 1 && l.overflow > 0;
      })
      .toBe(true);
    const folded = (await layout(page)).strip;

    // Opening what is missing grows the strip: the floor follows it, it is not measured once.
    await page.getByTestId('setup-strip-toggle').click();
    await expect.poll(async () => (await layout(page)).strip).toBeGreaterThan(folded + 20);
    await expect
      .poll(async () => {
        const l = await layout(page);
        return Math.abs(l.surface - (floor - l.strip)) <= 1;
      })
      .toBe(true);
  });

  test(`${SHORT_LANDSCAPE.width}×${SHORT_LANDSCAPE.height}: the no-network strip counts too, and gives its room back when it goes`, async ({
    page,
    context,
  }) => {
    await openStaff(page, SHORT_LANDSCAPE);
    const floor = await rootFloorPx(page);
    /** Height of every strip on the page, the blocking one and the no-network one. */
    const strips = () =>
      page.evaluate(() => {
        const table = document.querySelector('[data-testid="employees-table"]');
        const pageEl = table?.closest('.ion-page');
        return [
          ...(pageEl?.querySelectorAll<HTMLElement>('[data-testid="setup-strip"], [data-testid="offline-strip"]') ??
            []),
        ].reduce((sum, el) => sum + el.getBoundingClientRect().height, 0);
      });
    const surfaceIsNetOfStrips = async () => Math.abs((await layout(page)).surface - (floor - (await strips()))) <= 1;

    const setupOnly = await strips();
    await context.setOffline(true);
    try {
      await expect(page.getByTestId('offline-strip')).toBeVisible();
      await expect.poll(strips).toBeGreaterThan(setupOnly + 20);
      await expect.poll(surfaceIsNetOfStrips).toBe(true);
    } finally {
      await context.setOffline(false);
    }
    await expect(page.getByTestId('offline-strip')).toBeHidden();
    await expect.poll(strips).toBe(setupOnly);
    await expect.poll(surfaceIsNetOfStrips).toBe(true);
  });
});

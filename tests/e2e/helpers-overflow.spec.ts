// flow: e2e-overflow — FIX of the e2e harness (FIX-HUB-E2E-HORIZONTAL-SCROLL-CHECK-BLIND-TO-ION-CONTENT)
// The «no horizontal scroll» check of the specs read the document alone (how wide it is, against the window). Ionic pins the `body` to the window and every screen scrolls inside its `ion-content`, so a screen that runs
// past the right edge is cut there and the document never grows: with a 1600 px block on the modifier groups at 390,
// the check read 0 and the spec passed with the bar cut in its own capture (seen by the reviewer of hub#386).
// `horizontalOverflow(page)` (helpers.ts) is the one measure now: the document and every `ion-content` on screen. The
// checks here put a block wider than any window in each box the helper has to read and expect to see it.
import { expect, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, listReady, login, settled, shown } from './helpers';

const TASK = 'FIX-HUB-E2E-HORIZONTAL-SCROLL-CHECK-BLIND-TO-ION-CONTENT';

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** Wider than any window the e2e opens. */
const WIDE = 1600;

/** Puts a block `WIDE` px wide at the top of `content` (an `ion-content`), as a screen that does not fit its width. */
const widen = (content: ReturnType<Page['locator']>) =>
  content.evaluate((element, wide) => {
    const block = document.createElement('div');
    block.className = 'overflow-probe';
    block.textContent = `${wide} px wide`;
    block.style.cssText = `width: ${wide}px; height: 32px; background: #dc2626; color: #fff; font: 600 16px/32px sans-serif`;
    element.prepend(block);
  }, WIDE);

/** Takes the blocks of `widen` away. */
const narrow = (page: Page) => page.evaluate(() => document.querySelectorAll('.overflow-probe').forEach((block) => block.remove()));

/** The width of the scroll box of `content` (an `ion-content`): what the block has to fit in. */
const boxWidth = (content: ReturnType<Page['locator']>) =>
  content.evaluate((element) => element.shadowRoot?.querySelector('[part~="scroll"]')?.clientWidth ?? element.clientWidth);

test.describe('horizontalOverflow: the pixels of the page past the right edge', () => {
  test('e2e-overflow: it sees a block that runs past the right edge of the shown page’s ion-content, at 390, 834 and 1440', async ({
    page,
  }) => {
    await login(page, A, '/demo/items');
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await listReady(page);
      await settled(page);
      expect(await horizontalOverflow(page), `the demo list fits at ${size.label}`).toBe(0);
      const content = shown(page).locator('ion-content').first();
      await widen(content);
      await settled(page);
      const box = await boxWidth(content);
      expect(await horizontalOverflow(page), `the block past the page’s content at ${size.label}`).toBeGreaterThanOrEqual(WIDE - box);
      await capture(page, `${TASK}-${size.label}`);
      await narrow(page);
      await settled(page);
      expect(await horizontalOverflow(page), `the demo list fits again at ${size.label}`).toBe(0);
    }
  });

  test('e2e-overflow: it sees a block past the right edge of the pinned side menu’s ion-content at 1440', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page, A, '/demo/items');
    await listReady(page);
    const menu = page.locator('ion-menu.dash-menu ion-content').first();
    await expect(menu).toBeVisible();
    await widen(menu);
    await settled(page);
    const box = await boxWidth(menu);
    expect(box, 'the pinned menu is narrower than the window').toBeLessThan(1440);
    expect(await horizontalOverflow(page), 'the block past the menu’s content').toBeGreaterThanOrEqual(WIDE - box);
    await narrow(page);
    await settled(page);
    expect(await horizontalOverflow(page), 'the demo list fits again').toBe(0);
  });

  test('e2e-overflow: it sees a block past the right edge of an open sheet’s ion-content, at 390', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, A, '/demo/items');
    await listReady(page);
    // An inline sheet of Ionic over the page, its content holding the block: presented as the app's sheets are.
    await page.evaluate(async (wide) => {
      const modal = document.createElement('ion-modal') as HTMLElement & { present(): Promise<void> };
      modal.dataset.testid = 'overflow-sheet';
      const content = document.createElement('ion-content');
      const block = document.createElement('div');
      block.className = 'overflow-probe';
      block.style.cssText = `width: ${wide}px; height: 32px; background: #dc2626`;
      content.append(block);
      modal.append(content);
      document.querySelector('ion-app')?.append(modal);
      await modal.present();
    }, WIDE);
    const sheet = page.locator('ion-modal[data-testid=overflow-sheet] ion-content');
    await expect(sheet).toBeVisible();
    await settled(page);
    const box = await boxWidth(sheet);
    expect(await horizontalOverflow(page), 'the block past the sheet’s content').toBeGreaterThanOrEqual(WIDE - box);
    await page.evaluate(async () => {
      const modal = document.querySelector('ion-modal[data-testid=overflow-sheet]') as (HTMLElement & { dismiss(): Promise<boolean> }) | null;
      await modal?.dismiss();
      modal?.remove();
    });
    await settled(page);
    expect(await horizontalOverflow(page), 'the demo list fits once the sheet is gone').toBe(0);
  });

  test('e2e-overflow: it still sees a page without Ionic that scrolls sideways, as the public website', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.setContent('<!doctype html><body style="margin: 0"><main style="width: 100%">A page that fits</main></body>');
    expect(await horizontalOverflow(page), 'a page that fits').toBe(0);
    await page.setContent(`<!doctype html><body style="margin: 0"><main style="width: ${WIDE}px">A page too wide</main></body>`);
    expect(await horizontalOverflow(page), 'a page too wide for the window').toBe(WIDE - 390);
  });
});

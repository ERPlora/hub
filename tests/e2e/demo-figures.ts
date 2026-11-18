// The figures above the demo list («Open», «Done», «Lines»): what the page paints and when it first painted a given
// set. `demo.item.stats` is re-run by the same notices as `demo.item.list`, in the same pass of the stream.
import type { Page } from '@playwright/test';

import { shown } from './screen';

export type Figures = { open: number; done: number; lines: number };

/** The figures the page paints (the chips' `data-value`). */
export async function shownFigures(page: Page): Promise<Figures> {
  const value = async (name: keyof Figures) =>
    Number(await shown(page).locator(`[data-testid=demo-stats-${name}]`).getAttribute('data-value'));
  return { open: await value('open'), done: await value('done'), lines: await value('lines') };
}

/**
 * In-page probe: the `Date.now()` at which the figures first read `wanted` (see `figuresAt`). It also looks again when
 * a page stops being hidden: a list left for «New item» gets its figures while it is still hidden on the way back.
 */
export async function watchFigures(page: Page, wanted: Figures): Promise<void> {
  await page.evaluate((target) => {
    const w = window as unknown as { __figuresAt?: number };
    delete w.__figuresAt;
    const read = (name: string) =>
      Number(document.querySelector(`.ion-page:not(.ion-page-hidden) [data-testid=demo-stats-${name}]`)?.getAttribute('data-value'));
    const check = (): boolean => {
      const ok = read('open') === target.open && read('done') === target.done && read('lines') === target.lines;
      if (ok && w.__figuresAt === undefined) w.__figuresAt = Date.now();
      return ok;
    };
    if (check()) return;
    const observer = new MutationObserver(() => {
      if (check()) observer.disconnect();
    });
    observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['data-value', 'class'] });
  }, wanted);
}

export const figuresAt = (page: Page): Promise<number | undefined> =>
  page.evaluate(() => (window as unknown as { __figuresAt?: number }).__figuresAt);

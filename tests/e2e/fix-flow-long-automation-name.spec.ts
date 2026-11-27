// flow: FLOW-F02
// In «Your automations» a long automation name is read whole. The owner of hub `a` finds an automation with a long name
// (made for this run, through the API) at 390, 834 and 1440 px. In the table it wraps over several lines of its row,
// breaking only between words, with nothing of it hidden, and its `title` carries it too. On a phone (cards) the card's
// title ends in «…» past two lines and its «Name» is read whole. Never a word cut at the edge with no sign. No sideways
// scroll. Each width leaves its capture. The automation is deleted after it.
import { expect, type Locator, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, saveSessionForTheSweep, shown, untilStill } from './helpers';
import { signedIn } from './task-helpers';
import { linesOf, splitWords } from './words';

const KEY = 'FIX-HUB-FLOW-LONG-AUTOMATION-NAME-READ-WHOLE';
const SIZES = [
  { label: '390', width: 390, height: 844, cards: true },
  { label: '834', width: 834, height: 1112, cards: false },
  { label: '1440', width: 1440, height: 900, cards: false },
];

/**
 * Where the text of `name` is cut on screen, by itself or by a box around it that clips it (`overflow` other than
 * visible): '' when nothing cuts it. With `ellipsis: 'allowed'`, a cut by its own box that ends in «…» (one line,
 * `text-overflow: ellipsis`, or lines, `line-clamp`) does not count.
 */
function cutOf(name: Locator, ellipsis: 'allowed' | 'not allowed'): Promise<string> {
  return name.evaluate((el: HTMLElement, allowed: boolean) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const text = range.getBoundingClientRect();
    let right = Infinity;
    let bottom = Infinity;
    for (let box: HTMLElement | null = el; box && box !== document.body; box = box.parentElement) {
      const style = getComputedStyle(box);
      const edges = box.getBoundingClientRect();
      if (style.overflowX !== 'visible') right = Math.min(right, edges.right);
      if (style.overflowY !== 'visible') bottom = Math.min(bottom, edges.bottom);
    }
    const own = getComputedStyle(el);
    const ownEdges = el.getBoundingClientRect();
    const ownLine = own.overflowX !== 'visible' && own.textOverflow === 'ellipsis' && ownEdges.right <= right + 1;
    const clamp = own.webkitLineClamp;
    const ownLines = !!clamp && clamp !== 'none' && ownEdges.bottom <= bottom + 1;
    if (text.right > right + 1 && !(allowed && ownLine)) {
      return `cut on the right at ${Math.round(right)}px (its text runs to ${Math.round(text.right)}px; text-overflow: ${own.textOverflow})`;
    }
    if (text.bottom > bottom + 1 && !(allowed && ownLines)) {
      return `cut below at ${Math.round(bottom)}px (its text runs to ${Math.round(text.bottom)}px; line-clamp: ${clamp})`;
    }
    return '';
  }, ellipsis === 'allowed');
}

/** Whether the text of `name` runs past what is shown of it (cut, with «…» or not). */
function longerThanShown(name: Locator): Promise<boolean> {
  return name.evaluate((el: HTMLElement) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1);
}

/** The table: the whole name, over several lines that break only between words, and in its tooltip. */
async function expectReadWholeInTheRow(shownName: Locator, name: string, label: string): Promise<void> {
  expect(await cutOf(shownName, 'not allowed'), `the long name at ${label} px`).toBe('');
  expect(await linesOf(shownName), `the long name takes several lines at ${label} px`).toBeGreaterThan(1);
  expect(await splitWords(shownName), `words split over two lines at ${label} px`).toEqual([]);
  await expect(shownName).toHaveAttribute('title', name);
}

/** A card: its title ends in «…» past two lines; its «Name» is read whole. */
async function expectTitleClampedAndNameWhole(shownNames: Locator[], label: string): Promise<void> {
  const longer: boolean[] = [];
  for (const shownName of shownNames) {
    expect(await cutOf(shownName, 'allowed'), `the long name at ${label} px`).toBe('');
    longer.push(await longerThanShown(shownName));
  }
  expect(longer, `the card's title ends in «…» at ${label} px`).toContain(true);
  expect(longer, `the whole name is read on its card at ${label} px`).toContain(false);
}

for (const size of SIZES) {
  test(`FLOW-F02 at ${size.label}: a long automation name is read whole, never cut mid-word`, async ({ browser }) => {
    const stamp = Date.now().toString(36);
    const name = `E2E Flow ${stamp} Tell the customer by WhatsApp when their reservation changes and remind them the day before`;
    const { context, page } = await signedIn(browser, '/flow/automations', undefined, { width: size.width, height: size.height });
    let flowId = '';
    try {
      const created = await api<{ id: string }>(context, A, 'POST', '/flow/flows', {
        name,
        trigger: { kind: 'event', event: 'customer.customer.created' },
        steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: `E2E Flow ${stamp}` } }],
      });
      expect(created.status, JSON.stringify(created.data)).toBe(201);
      flowId = created.data.id;

      await page.goto(`${A}/flow/automations`);
      const list = shown(page).locator('[data-testid=flow-list-section]');
      await list.locator('[data-testid=flow-list-search] input').fill(stamp);
      const row = list.locator('[data-testid=flow-list-row]').filter({ hasText: stamp });
      await expect(row).toHaveCount(1);
      // The table shows the name once; a card twice: its title and its «Name».
      const shownNames = row.getByText(name, { exact: true });
      await expect(shownNames).toHaveCount(size.cards ? 2 : 1);
      await untilStill(page);
      await shownNames.first().scrollIntoViewIfNeeded();

      if (size.cards) await expectTitleClampedAndNameWhole(await shownNames.all(), size.label);
      else await expectReadWholeInTheRow(shownNames, name, size.label);

      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await capture(page, `${KEY}-${size.label}`);
      await saveSessionForTheSweep(context);
    } finally {
      if (flowId) await api(context, A, 'POST', '/flow/flows/delete', { id: flowId });
      await context.close();
    }
  });
}

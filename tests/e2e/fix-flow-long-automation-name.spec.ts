// flow: FLOW-F02
// — On a tablet (834 px), «Your automations» cut a long name in the middle of a word and with no «…» («Tell the
// customer by WhatsApp when thei»): the cell gives its own span one line with «…», but the name's span stacks the name
// over «when it starts», and the name inside it ran on to the edge, where the span clipped it. The owner of hub `a`
// finds an automation with a long name (made for this run, through the API) at 390, 834 and 1440 px: in the table it
// is one line ending in «…», the whole name in its `title`; on a phone (cards) its title wraps and, past two lines,
// ends in «…». Never a word cut at the edge with no sign. No sideways scroll. Each width leaves its capture
// `FIX-HUB-FLOW-LONG-AUTOMATION-NAME-CUT-MID-WORD-ON-TABLET-<width>`. The automation is deleted after it.
import { expect, type Locator, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, shown, untilStill } from './helpers';
import { signedIn } from './task-helpers';

const KEY = 'FIX-HUB-FLOW-LONG-AUTOMATION-NAME-CUT-MID-WORD-ON-TABLET';
const SIZES = [
  { label: '390', width: 390, height: 844, cards: true },
  { label: '834', width: 834, height: 1112, cards: false },
  { label: '1440', width: 1440, height: 900, cards: false },
];

/**
 * How the text of `name` is cut on screen: '' when it is read whole, or when the box that cuts it is its own and ends
 * it in «…» (one line, `text-overflow: ellipsis`, or lines, `line-clamp`). Otherwise what cuts it and where: a box
 * around it that clips it (`overflow` other than visible) with no «…» of its own cuts a word at the edge.
 */
function cutWithoutEllipsis(name: Locator): Promise<string> {
  return name.evaluate((el: HTMLElement) => {
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
    const clipsItself = own.overflowX !== 'visible';
    if (text.right > right + 1) {
      if (own.textOverflow !== 'ellipsis' || !clipsItself || ownEdges.right > right + 1) {
        return `cut on the right at ${Math.round(right)}px with no «…» (its text runs to ${Math.round(text.right)}px; text-overflow: ${own.textOverflow})`;
      }
    }
    if (text.bottom > bottom + 1) {
      const clamp = own.webkitLineClamp;
      if (!clamp || clamp === 'none' || ownEdges.bottom > bottom + 1) {
        return `cut below at ${Math.round(bottom)}px with no «…» (its text runs to ${Math.round(text.bottom)}px)`;
      }
    }
    return '';
  });
}

/** Whether the text of `name` runs past what is shown of it (cut, with «…» or not). */
function longerThanShown(name: Locator): Promise<boolean> {
  return name.evaluate((el: HTMLElement) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1);
}

for (const size of SIZES) {
  test(`FLOW-F02 at ${size.label}: a long automation name ends in «…», never cut mid-word`, async ({ browser }) => {
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

      const longer: boolean[] = [];
      for (const shownName of await shownNames.all()) {
        await shownName.scrollIntoViewIfNeeded();
        expect(await cutWithoutEllipsis(shownName), `the long name at ${size.label} px`).toBe('');
        longer.push(await longerThanShown(shownName));
      }
      // The premise: the name does not fit, so this width really shows how it is cut.
      expect(longer, `the name is longer than what ${size.label} px shows of it`).toContain(true);
      if (size.cards) {
        // A card's title ends in «…» past two lines; its «Name» is read whole.
        expect(longer, `the whole name is read on its card at ${size.label} px`).toContain(false);
      } else {
        // The table: the whole name in its tooltip (and for whoever reads it aloud).
        await expect(shownNames).toHaveAttribute('title', name);
      }

      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await capture(page, `${KEY}-${size.label}`);
    } finally {
      if (flowId) await api(context, A, 'POST', '/flow/flows/delete', { id: flowId });
      await context.close();
    }
  });
}

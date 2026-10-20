// flow: ui:DataTable — FIX-UI-DATATABLE-CARD-LONG-VALUE-CLIP (hub#91, seen by the worker of APP-STAFF):
// on a phone, where a list becomes cards, a value with no spaces (a 54-character email in Staff ›
// Members) ran past the right edge of its card and was cut with no «…». No value leaves its card: a
// word too long for it ends in «…» (the whole value stays in its title and in the record the card
// opens), as the list cell does at 834 and 1440 px (erplora-old/hub#2717 was that cell, cut mid-word).
// With ui 8ea0289 the text ran past the card's content box and only ion-card's own clip hid it.
import { type Browser, expect, type Locator, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { settled, VIEWPORTS } from './schedule-helpers';

const TAG = 'E2ELong';
const EMAIL = 'fix.ui.datatable.card.long.value.clips.e2e@example.com';

function cleanup(): void {
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from staff_timeoff where member_id in (${members})`,
      `delete from staff_scheduleday where schedule_id in (select id from staff_schedule where member_id in (${members}))`,
      `delete from staff_schedule where member_id in (${members})`,
      `delete from staff_member where first_name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeEach(cleanup);
test.afterAll(cleanup);

async function signedIn(browser: Browser, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/staff/members');
  return { context, page };
}

/** How the email of the seeded record is painted: in a card (390) or in a list cell (834, 1440).
 *  `visibleRight` is where the text stops being painted: its own right edge, cut by every box between
 *  it and the card (or the cell) that clips; `limit` is the right edge of the card's content box (or of
 *  the cell). `clipper` is the box nearest to the text that clips it, with its «…» and its title. */
async function probe(table: Locator, email: string) {
  return table.evaluate((root, value) => {
    const holder = [...root.querySelectorAll('.data-table__card, .data-table__row--data')].find((el) => el.textContent?.includes(value));
    if (!holder) return null;
    const text = [...holder.querySelectorAll('*')]
      .flatMap((el) => [...el.childNodes])
      .find((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim() === value);
    if (!text?.parentElement) return null;
    const card = holder.classList.contains('data-table__card');
    const frame = card ? (holder.querySelector('.data-table__card-body') as HTMLElement) : (text.parentElement.closest('[role=cell]') as HTMLElement);
    const range = document.createRange();
    range.selectNodeContents(text);
    let visibleRight = range.getBoundingClientRect().right;
    let clipper: HTMLElement | null = null;
    for (let el: HTMLElement | null = text.parentElement; el; el = el.parentElement) {
      if (getComputedStyle(el).overflowX !== 'visible') {
        visibleRight = Math.min(visibleRight, el.getBoundingClientRect().right);
        clipper ??= el;
      }
      if (el === holder) break;
    }
    const box = frame.getBoundingClientRect();
    const limit = card ? box.right - parseFloat(getComputedStyle(frame).paddingRight) : box.right;
    return {
      card,
      visibleRight: Math.round(visibleRight * 10) / 10,
      limit: Math.round(limit * 10) / 10,
      clipped: !!clipper && clipper.scrollWidth > clipper.clientWidth,
      ellipsis: clipper ? getComputedStyle(clipper).textOverflow : null,
      clipperIsHolder: clipper === holder,
      title: text.parentElement.getAttribute('title'),
    };
  }, email);
}

for (const vp of VIEWPORTS) {
  test(`ui:DataTable at ${vp.label}: a long email stays inside its card (or cell) and ends in «…»`, async ({ browser }) => {
    expect(EMAIL).toHaveLength(54);
    const owner = await signedIn(browser, { width: vp.width, height: vp.height });
    try {
      const { context, page } = owner;
      const name = `${TAG}${vp.label} Long`;
      const created = await api(context, A, 'POST', '/staff/members', { first_name: `${TAG}${vp.label}`, last_name: 'Long', email: EMAIL });
      expect(created.status, 'the seeded staff record').toBe(201);
      await page.goto(`${A}/staff/members`);
      const view = shown(page);
      const row = view.locator('[data-testid=staff-members-row]', { hasText: name }).first();
      await expect(row).toBeVisible();
      await expect(row).toContainText(EMAIL.slice(0, 20));
      await settled(page);
      const table = view.locator('.data-table').first();
      // The ladder (W-19) settles in a few frames after the last resize; a phone always gets cards.
      await expect.poll(() => probe(table, EMAIL).then((seen) => seen !== null)).toBe(true);
      await settled(page);
      const seen = await probe(table, EMAIL);
      expect(seen, 'the email is painted').not.toBeNull();
      if (vp.width <= 640) expect(seen!.card, 'a phone gets the cards').toBe(true);
      expect(seen!.visibleRight, `the email ends inside its ${seen!.card ? 'card' : 'cell'} at ${vp.label}`).toBeLessThanOrEqual(seen!.limit + 0.5);
      // The box that cuts the text is the value's own (never the card's edge), and it says so with «…».
      expect(seen!.clipperIsHolder, 'the card (or row) itself is not what cuts the email').toBe(false);
      if (seen!.clipped) expect(seen!.ellipsis).toBe('ellipsis');
      if (vp.width <= 640) expect(seen!.clipped, 'on a phone the 54 characters do not fit: «…»').toBe(true);
      expect(seen!.title).toBe(EMAIL);
      await row.scrollIntoViewIfNeeded();
      await page.screenshot({ path: shot(`FIX-UI-DATATABLE-CARD-LONG-VALUE-CLIP-${vp.label}`) });
    } finally {
      await owner.context.close();
    }
  });
}

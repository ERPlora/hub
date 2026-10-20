// flow: ui:DataTable — FIX-UI-DATATABLE-STICKY-ACTIONS-OVERLAP (hub#94, mutant M6 of attendance-flows):
// the pinned row actions («⋮») never cover the last column of a list. A list that offers cards gives
// up, in this order, its `low` columns, its row actions and then the list itself (W-19): it never stays
// a list scrolled sideways under «⋮». Only a list WITHOUT cards may scroll inside its box, and then it
// says so (`.data-table__scroll--overflow`, the shadow of the pinned edge).
// The list is Time clock › Records with every column picked back in the column chooser, as a person
// does: at 834px it does not fit even folded. With ui 7cfc81c it stayed a list with «Location» under
// «⋮» (the folded «Actions» header was written without a render, and the ladder waited for one).
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { settled, VIEWPORTS } from './schedule-helpers';

const TAG = 'E2EStk';
const ZONE = 'Europe/Madrid';
const RECORDS = `select id from attendance_record where member_id in (select id from staff_member where first_name like '${TAG}%')`;

function cleanup(): void {
  psql(
    [
      `delete from attendance_correction where record_id in (${RECORDS})`,
      `delete from attendance_break where record_id in (${RECORDS})`,
      `delete from attendance_record where id in (${RECORDS})`,
      `delete from staff_member where first_name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeEach(cleanup);
test.afterAll(cleanup);

async function signedIn(browser: Browser, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US', timezoneId: ZONE });
  const page = await context.newPage();
  await login(page, A, '/attendance/records');
  return { context, page };
}

/** Two working days of the team: one closed, one forgotten 13 hours ago (it waits for review). */
async function seedDays(page: Page, label: string): Promise<void> {
  const context = page.context();
  const member = async (first: string): Promise<string> => {
    const created = await api<{ id: string }>(context, A, 'POST', '/staff/members', { first_name: first, last_name: 'Clock' });
    expect(created.status, `staff record ${first}`).toBe(201);
    return created.data.id;
  };
  const bea = await member(`${TAG}${label}Bea`);
  const cid = await member(`${TAG}${label}Cid`);
  expect((await api(context, A, 'POST', '/attendance/clock_in', { member: `${TAG}${label}Bea Clock` })).status).toBe(200);
  expect((await api(context, A, 'POST', '/attendance/clock_out', { member_id: bea })).status).toBe(200);
  psql(
    `insert into attendance_record (id, work_date, clock_in_at, status, source, note, created_at, updated_at, member_id) values (gen_random_uuid(), ((now() - interval '13 hours') at time zone '${ZONE}')::date, now() - interval '13 hours', 'open', 'shared', '', now(), now(), '${cid}')`,
  );
}

/** Picks every column back in the list's column chooser (the person's own choice). */
async function pickEveryColumn(page: Page, table: Locator): Promise<void> {
  await table.locator('ion-select.data-table__columns-select').click();
  const options = page.locator('ion-popover ion-checkbox');
  await expect(options.first()).toBeVisible();
  for (const option of await options.all()) {
    if ((await option.getAttribute('aria-checked')) !== 'true' && !(await option.evaluate((el) => (el as HTMLInputElement).checked))) await option.click();
  }
  await page.keyboard.press('Escape');
  await expect(options.first()).toBeHidden();
}

/** What the list paints: cards or a list, whether it scrolls sideways, and per visible row how far the
 *  content of its last data cell runs under the pinned actions (px; <= 0 = clear of them). */
async function probe(table: Locator) {
  return table.evaluate((root) => {
    const scroll = root.querySelector('.data-table__scroll');
    const covered: number[] = [];
    for (const row of root.querySelectorAll('.data-table__row--data')) {
      const actions = row.querySelector('.data-table__cell--actions');
      const cells = [...row.querySelectorAll(':scope > [role=cell]:not(.data-table__cell--actions)')];
      const last = cells[cells.length - 1];
      if (!actions || !last) continue;
      const content = document.createRange();
      content.selectNodeContents(last);
      const right = Math.max(...[...content.getClientRects()].map((r) => r.right), -Infinity);
      if (Number.isFinite(right)) covered.push(Math.round((right - actions.getBoundingClientRect().left) * 10) / 10);
    }
    return {
      cards: !!root.querySelector('.data-table__cards'),
      overflow: !!scroll?.classList.contains('data-table__scroll--overflow'),
      covered: covered.filter((px) => px > 0),
      rows: root.querySelectorAll('.data-table__row--data, .data-table__card').length,
    };
  });
}

for (const vp of VIEWPORTS) {
  test(`ui:DataTable at ${vp.label}: the pinned «⋮» never covers the last column of a list that offers cards`, async ({ browser }) => {
    const owner = await signedIn(browser, { width: vp.width, height: vp.height });
    try {
      const page = owner.page;
      await seedDays(page, vp.label);
      await page.goto(`${A}/attendance/records`);
      const view = shown(page);
      await expect(view.locator(`[data-testid=attendance-records-row]`, { hasText: `${TAG}${vp.label}Cid Clock` }).first()).toBeVisible();
      const table = view.locator('.data-table').first();
      if (vp.width > 640) {
        await pickEveryColumn(page, table);
        await expect(table.locator('[role=columnheader]', { hasText: 'Location' }).or(table.locator('.data-table__cards'))).toBeVisible();
      }
      await settled(page);
      // The ladder settles in a few frames after the last resize; the list never ends under «⋮».
      await expect.poll(() => probe(table).then(({ overflow, covered }) => ({ overflow, covered }))).toEqual({ overflow: false, covered: [] });
      const seen = await probe(table);
      expect(seen.rows, 'the seeded days are on screen').toBeGreaterThanOrEqual(2);
      expect(seen.cards, `a list too wide for its box hands over to the cards at ${vp.label}`).toBe(vp.width < 1440);
      await page.screenshot({ path: shot(`FIX-UI-DATATABLE-STICKY-ACTIONS-OVERLAP-${vp.label}`) });
    } finally {
      await owner.context.close();
    }
  });
}

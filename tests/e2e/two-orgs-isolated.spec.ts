// PoC §8.1 (second half): a write in business `b` never reaches the open screens of `a`, and the
// other way round. Since S2a (round 2026-10-30 of PLAN-DB) each business has its own database, so a
// reload does not show them either: b's row is in b's database and nowhere in a's (phase 1 shared the
// rows, and only the live notice was per business).
import { type Page, expect, test } from '@playwright/test';

import { A, B, createViaPage, hostPage, listReady, psql, record, row, rowNames, shot, uniqueName, watchForRow } from './helpers';

const QUIET_MS = 2000;

/** Creates `name` on `writer` and checks `other` stays as it was for 2 s after the writer saw it. */
async function writeAndWatch(writer: Page, other: Page, name: string) {
  const before = await rowNames(other);
  await watchForRow(other, name);
  await createViaPage(writer, name);
  await expect(row(writer, name)).toBeVisible({ timeout: 5000 });
  const writerSawAt = Date.now();
  const samples: number[] = [];
  while (Date.now() - writerSawAt < QUIET_MS) {
    samples.push((await rowNames(other)).length);
    await other.waitForTimeout(200);
  }
  const after = await rowNames(other);
  const leaked = await other.evaluate((n) => (window as unknown as { __rowSeen?: Record<string, number> }).__rowSeen?.[n], name);
  return { before: before.length, after: after.length, samples, sameRows: JSON.stringify(before) === JSON.stringify(after), leaked: leaked !== undefined };
}

test('a write in b does not reach a within 2 s, and the other way round', async ({ browser }) => {
  const a = await hostPage(browser, A);
  const b = await hostPage(browser, B);
  await listReady(a.page);
  await listReady(b.page);

  const nameB = uniqueName('Only b');
  const bToA = await writeAndWatch(b.page, a.page, nameB);
  await a.page.screenshot({ path: shot('03-a-after-write-in-b') });
  await b.page.screenshot({ path: shot('03-b-after-own-write') });

  const nameA = uniqueName('Only a');
  const aToB = await writeAndWatch(a.page, b.page, nameA);
  await b.page.screenshot({ path: shot('03-b-after-write-in-a') });

  // Each business's rows live in its own database: a reload of `a` never shows b's row, nor of `b` a's, and each row
  // is in its business's database only.
  await a.page.reload();
  await listReady(a.page);
  const aReloadShowsB = (await rowNames(a.page)).includes(nameB);
  await b.page.reload();
  await listReady(b.page);
  const bReloadShowsA = (await rowNames(b.page)).includes(nameA);
  const count = (name: string, hub: string) => Number(psql(`select count(*) from demo_item where name = '${name}'`, hub));
  const rows = { bInA: count(nameB, 'a'), bInB: count(nameB, 'b'), aInA: count(nameA, 'a'), aInB: count(nameA, 'b') };

  record('03-two-orgs-isolated', { quietMs: QUIET_MS, bToA, aToB, aReloadShowsB, bReloadShowsA, rows });
  expect(bToA.sameRows).toBe(true);
  expect(bToA.leaked).toBe(false);
  expect(aToB.sameRows).toBe(true);
  expect(aToB.leaked).toBe(false);
  expect(aReloadShowsB).toBe(false);
  expect(bReloadShowsA).toBe(false);
  expect(rows).toEqual({ bInA: 0, bInB: 1, aInA: 1, aInB: 0 });

  await a.context.close();
  await b.context.close();
});

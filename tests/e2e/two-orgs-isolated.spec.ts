// PoC §8.1 (second half): a write in business `b` never reaches the open screens of `a`, and the
// other way round. Phase 1 shares the rows (one database), so a reload DOES show them: only the
// live notice is per business (WORKBOOK «Antes de empezar»).
import { type Page, expect, test } from '@playwright/test';

import { A, B, createViaPage, hostPage, listReady, record, row, rowNames, shot, uniqueName, watchForRow } from './helpers';

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

  // Control: the rows exist for both (shared database in phase 1); a reload of `a` shows b's row.
  await a.page.reload();
  await listReady(a.page);
  const aReloadShowsB = (await rowNames(a.page)).includes(nameB);

  record('03-two-orgs-isolated', { quietMs: QUIET_MS, bToA, aToB, aReloadShowsB });
  expect(bToA.sameRows).toBe(true);
  expect(bToA.leaked).toBe(false);
  expect(aToB.sameRows).toBe(true);
  expect(aToB.leaked).toBe(false);
  expect(aReloadShowsB).toBe(true);

  await a.context.close();
  await b.context.close();
});

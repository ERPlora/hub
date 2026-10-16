// PoC §8.1 (first half) and DEMO-F05: two tabs of `a`; an item created in tab 1 through «New item»
// shows up in tab 2 within 1 s, without a reload and without moving tab 2's focus.
import { expect, test } from '@playwright/test';

import { A, appearedAt, createViaPage, listReady, login, record, row, shot, shown, uniqueName, watchForRow } from './helpers';
import { recordResponses, responseEnd } from './resource-timing';

const ROUNDS = 3;

test('create in tab 1 → tab 2 paints the row in < 1 s, no reload, focus kept', async ({ context }) => {
  const tab1 = await context.newPage();
  await recordResponses(tab1);
  await login(tab1, A);
  const tab2 = await context.newPage();
  await tab2.goto('/demo/items');
  await listReady(tab1);
  await listReady(tab2);
  await tab2.evaluate(() => ((window as unknown as { __doc: string }).__doc = 'tab2-original'));
  // Tab 2 is "someone else's tablet" with the cursor in the search box.
  await shown(tab2).locator('ion-searchbar input').focus();

  const rounds: { name: string; clickToTab2Ms: number; responseToTab2Ms: number; clickToTab1Ms: number }[] = [];
  for (let i = 0; i < ROUNDS; i += 1) {
    const name = uniqueName(`Live ${i + 1}`);
    await watchForRow(tab1, name);
    await watchForRow(tab2, name);
    await createViaPage(tab1, name);
    await expect(row(tab2, name)).toBeVisible({ timeout: 5000 });
    await expect(row(tab1, name)).toBeVisible();

    const clicked = await tab1.evaluate(() => {
      const w = window as unknown as { __saveClickedAt?: number; __saveClickedPageMs?: number };
      return { at: w.__saveClickedAt, pageMs: w.__saveClickedPageMs };
    });
    const tab2At = await appearedAt(tab2, name);
    const tab1At = await appearedAt(tab1, name);
    expect(clicked.at, `${name}: tab 1 timed the click on «Save»`).toBeDefined();
    expect(tab2At, `${name}: tab 2 timed its row`).toBeDefined();
    expect(tab1At, `${name}: tab 1 timed its row`).toBeDefined();
    // The POST that click sent, from the recorder: Vite's dev modules fill the page's resource timing buffer.
    const createdAt = (await responseEnd(tab1, '/api/demo/items', { since: clicked.pageMs })).epochMs;
    rounds.push({
      name,
      clickToTab2Ms: tab2At! - clicked.at!,
      responseToTab2Ms: Math.round(tab2At! - createdAt),
      clickToTab1Ms: tab1At! - clicked.at!,
    });
  }
  await tab1.screenshot({ path: shot('02-tab1-after-create') });
  await tab2.screenshot({ path: shot('02-tab2-live-row') });

  const visibility = [await tab1.evaluate(() => document.visibilityState), await tab2.evaluate(() => document.visibilityState)];
  const tab2Doc = await tab2.evaluate(() => (window as unknown as { __doc?: string }).__doc);
  const tab2Focus = await tab2.evaluate(() => document.activeElement?.closest('ion-searchbar') !== null);
  record('02-two-tabs-live', { rounds, visibility, tab2SameDocument: tab2Doc === 'tab2-original', tab2SearchFocused: tab2Focus });

  for (const r of rounds) expect(r.clickToTab2Ms, r.name).toBeLessThan(1000);
  expect(tab2Doc).toBe('tab2-original');
  expect(tab2Focus).toBe(true);
});

// DEMO-F05: two tabs of `a`; an item created in tab 1 through «New item» shows up in tab 2 without a reload and
// without moving tab 2's focus. The second of the flow is checked against what the same notice brings: both lists are
// open and get the row from it, and on each tab the figures above the list come in the same pass. A loaded machine
// delays all of it alike (1.8 s from the click on both tabs, seen), so on each tab the row less than 1 s after its own
// figures, and tab 2 less than 1 s after tab 1, hold whatever the load; a list or a tab sitting on the notice does not.
import { expect, test } from '@playwright/test';

import { type Figures, figuresAt, shownFigures, watchFigures } from './demo-figures';
import { A, api, login, record, runningTimeout, shot, shown, uniqueName } from './helpers';
import { appearedAt, createViaPage, listReady, row, watchForRow } from './demo-items';
import { recordResponses, responseEnd } from './resource-timing';

const ROUNDS = 3;

test('create in tab 1 → tab 2 paints the row with the same notice, < 1 s, no reload, focus kept @smoke', async ({ context }) => {
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

  const tabs = [tab1, tab2];
  const rounds: {
    name: string;
    clickToTab1Ms: number;
    clickToTab2Ms: number;
    responseToTab2Ms: number;
    tab1ToTab2Ms: number;
    figuresToRowMs: number[];
  }[] = [];
  for (let i = 0; i < ROUNDS; i += 1) {
    const name = uniqueName(`Live ${i + 1}`);
    const { open, done, lines } = (await api<Figures>(context, A, 'GET', '/demo/items/stats')).data;
    const before = { open, done, lines };
    const after = { ...before, open: open + 1 };
    for (const tab of tabs) {
      await expect.poll(() => shownFigures(tab)).toEqual(before);
      await watchFigures(tab, after);
      await watchForRow(tab, name);
    }
    await createViaPage(tab1, name);
    // The notice reaches tab 1 as late as the machine makes it: waited for as long as the test has. Everything else
    // comes in the same pass or less than 1 s later, so from there the config's wait is plenty.
    await expect.poll(() => shownFigures(tab1), { timeout: runningTimeout() }).toEqual(after);
    for (const tab of tabs) {
      await expect.poll(() => shownFigures(tab)).toEqual(after);
      await expect(row(tab, name)).toBeVisible();
    }

    const clicked = await tab1.evaluate(() => {
      const w = window as unknown as { __saveClickedAt?: number; __saveClickedPageMs?: number };
      return { at: w.__saveClickedAt, pageMs: w.__saveClickedPageMs };
    });
    const tab2At = await appearedAt(tab2, name);
    const tab1At = await appearedAt(tab1, name);
    expect(clicked.at, `${name}: tab 1 timed the click on «Save»`).toBeDefined();
    expect(tab2At, `${name}: tab 2 timed its row`).toBeDefined();
    expect(tab1At, `${name}: tab 1 timed its row`).toBeDefined();
    const figuresAtTab = [await figuresAt(tab1), await figuresAt(tab2)];
    expect(figuresAtTab, `${name}: both tabs timed their figures`).not.toContain(undefined);
    // The POST that click sent, from the recorder: Vite's dev modules fill the page's resource timing buffer.
    const createdAt = (await responseEnd(tab1, '/api/demo/items', { since: clicked.pageMs })).epochMs;
    rounds.push({
      name,
      clickToTab1Ms: tab1At! - clicked.at!,
      clickToTab2Ms: tab2At! - clicked.at!,
      responseToTab2Ms: Math.round(tab2At! - createdAt),
      tab1ToTab2Ms: tab2At! - tab1At!,
      figuresToRowMs: [tab1At! - figuresAtTab[0]!, tab2At! - figuresAtTab[1]!],
    });
  }
  await tab1.screenshot({ path: shot('02-tab1-after-create') });
  await tab2.screenshot({ path: shot('02-tab2-live-row') });

  const visibility = [await tab1.evaluate(() => document.visibilityState), await tab2.evaluate(() => document.visibilityState)];
  const tab2Doc = await tab2.evaluate(() => (window as unknown as { __doc?: string }).__doc);
  const tab2Focus = await tab2.evaluate(() => document.activeElement?.closest('ion-searchbar') !== null);
  record('02-two-tabs-live', { rounds, visibility, tab2SameDocument: tab2Doc === 'tab2-original', tab2SearchFocused: tab2Focus });

  for (const r of rounds) {
    const said = `${r.name}: ${JSON.stringify(r)}`;
    for (const late of r.figuresToRowMs) expect(late, `${said}, the row after the figures of its tab`).toBeLessThan(1000);
    expect(r.tab1ToTab2Ms, `${said}, tab 2 after tab 1`).toBeLessThan(1000);
  }
  expect(tab2Doc).toBe('tab2-original');
  expect(tab2Focus).toBe(true);
});

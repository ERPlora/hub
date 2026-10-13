// PoC §8.8 (first half): every stream of the process shares ONE `LISTEN` connection on the control
// database (`application_name = 'live-listener'`), and it stays when the streams go. If it is killed
// (`pg_terminate_backend`) the Listener reconnects and the open screens keep receiving changes.
import { type Page, expect, test } from '@playwright/test';

import { A, B, createItem, hostPage, listenerRows, listReady, psql, record, row, uniqueName, waitFor } from './helpers';

test('3 pages on a + 2 on b → one live-listener row; closing them keeps it; a killed one comes back', async ({ browser }) => {
  const before = listenerRows();
  const a = await hostPage(browser, A);
  const b = await hostPage(browser, B);
  const pages: Page[] = [a.page, b.page];
  for (let i = 0; i < 2; i += 1) pages.push(await a.context.newPage());
  pages.push(await b.context.newPage());
  for (const p of pages.slice(2)) await p.goto('/demo/items');
  for (const p of pages) await listReady(p);
  const open = listenerRows();

  // Kill the listener: it comes back with a new backend and the screens still get live changes.
  const killed = open[0]?.pid;
  psql(`select pg_terminate_backend(${killed})`);
  const backInMs = await waitFor(() => {
    const rows = listenerRows();
    return rows.length === 1 && rows[0].pid !== killed;
  }, 60_000, 500);
  const afterKill = listenerRows();
  const name = uniqueName('After listener kill');
  await createItem(a.context, A, name);
  const aPages = [pages[0], pages[2], pages[3]];
  for (const p of aPages) await expect(row(p, name)).toBeVisible({ timeout: 10_000 });

  await a.context.close();
  await b.context.close();
  await new Promise((r) => setTimeout(r, 3000));
  const closed = listenerRows();

  record('09-connections', {
    before,
    withThreeOnAandTwoOnB: open,
    killedPid: killed,
    listenerBackInMs: backInMs,
    afterKill,
    aPagesGotChangeAfterKill: aPages.length,
    afterClosingAll: closed,
  });
  expect(open).toHaveLength(1);
  expect(afterKill).toHaveLength(1);
  expect(afterKill[0].pid).not.toBe(killed);
  expect(closed).toHaveLength(1);
});

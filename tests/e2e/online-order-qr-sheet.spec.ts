// The tables' QR codes of Online orders, end to end in a browser: the owner opens «QR codes», gives the tables without a
// QR their first one at once, prints the sheet (one card per table, drawn in the browser), regenerates the QR of one
// table after confirming that the printed one stops working, and prints that table alone. The browser's print dialog
// is stood in for by a counter that reads the paper the page hands it; the run's zone and tables are deleted after it.
// flow: ONLINE_ORDER-F01
// flow: ONLINE_ORDER-F02

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, saveSessionForTheSweep, shown, turnOffTurnedOn, turnOnMissing, untilStill } from './helpers';
import { stamp } from './sale-helpers';
import { rowAction } from './service-helpers';
import { toasts } from './toast-helpers';

const RUN = stamp();
const ZONE = `e2e QR ${RUN}`;
const LIST = 'online-order-qr';
const SIZES = [
  { label: 'desktop', width: 1440, height: 900 },
  { label: 'tablet-landscape', width: 1280, height: 800 },
  { label: 'phone', width: 375, height: 667 },
] as const;

interface CodeRow {
  table_id: string;
  number: string;
  code: string | null;
  url: string | null;
}

/** What the page handed the browser to print: each card's words and whether its QR is a drawn image. */
interface Printed {
  count: number;
  cards: { words: string; drawn: boolean }[];
}

let context: BrowserContext;
let page: Page;
const turnedOn: string[] = [];
let zoneId = '';
const tables: { id: string; number: string }[] = [];

async function codes(): Promise<CodeRow[]> {
  const answer = await api<{ rows: CodeRow[] }>(context, A, 'GET', '/online_order/qr_codes?limit=100');
  expect(answer.status, JSON.stringify(answer.data)).toBe(200);
  return answer.data.rows.filter((row) => tables.some((table) => table.id === row.table_id));
}

const row = (id: string) => shown(page).locator(`[data-testid=${LIST}-row][data-id="${id}"]`);
const printed = () => page.evaluate(() => (window as unknown as { printed: Printed }).printed);

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({ viewport: SIZES[0] });
  page = await context.newPage();
  await login(page, A, '/');
  await saveSessionForTheSweep(context);
  await turnOnMissing(context, A, ['online_order'], turnedOn);
  const zone = await api<{ id: string }>(context, A, 'POST', '/table/zones', { name: ZONE });
  expect(zone.status, JSON.stringify(zone.data)).toBe(201);
  zoneId = zone.data.id;
  for (const number of ['901', '902']) {
    const made = await api<{ id: string }>(context, A, 'POST', '/table/tables', { zone_id: zoneId, number });
    expect(made.status, JSON.stringify(made.data)).toBe(201);
    tables.push({ id: made.data.id, number });
  }
  // The browser's print dialog, stood in for: it reads the paper handed to it, as the printer would.
  await context.addInitScript(() => {
    const state = window as unknown as { printed: Printed };
    state.printed = { count: 0, cards: [] };
    window.print = () => {
      const cards = [...document.querySelectorAll('body.ep-printing > .ep-print-root [data-testid=online-order-qr-sheet-card]')];
      state.printed = {
        count: state.printed.count + 1,
        cards: cards.map((card) => ({
          words: [...card.querySelectorAll('p')].map((line) => (line.textContent ?? '').trim()).join(' '),
          drawn: (card.querySelector('img')?.getAttribute('src') ?? '').startsWith('data:image/png;base64,'),
        })),
      };
    };
  });
});

test.afterAll(async () => {
  try {
    const ids = tables.map((table) => `'${table.id}'`).join(', ');
    if (ids) psql(`delete from online_order_tablecode where table_id in (${ids})`);
    for (const table of tables) await api(context, A, 'POST', '/table/tables/delete', { id: table.id });
    if (zoneId) await api(context, A, 'POST', '/table/zones/delete', { id: zoneId });
  } finally {
    await turnOffTurnedOn(context, A, turnedOn);
    await context.close();
  }
});

test('ONLINE_ORDER-F01, F02: the missing QR codes at once, the sheet printed, one QR regenerated and printed alone', async () => {
  await page.goto(`${A}/online_order/qr-codes`);
  const [first, second] = tables;
  await expect(row(first.id)).toContainText('No QR yet');
  await expect(row(second.id)).toContainText(ZONE);
  await expect(shown(page).locator(`[data-testid=${LIST}-missing]`)).toContainText('no QR yet');

  // ONLINE_ORDER-F01: the tables without a code get their first one, without asking.
  await shown(page).locator(`[data-testid=${LIST}-generate-missing]`).click();
  await expect(toasts(page).last()).toContainText('have their QR');
  await expect.poll(async () => (await codes()).every((one) => one.code)).toBe(true);
  const before = await codes();
  await expect(row(first.id)).toContainText(before.find((one) => one.table_id === first.id)!.url!);

  for (const size of SIZES) {
    await page.setViewportSize(size);
    await expect(row(first.id)).toBeVisible();
    await untilStill(page);
    await capture(page, `ONLINE-ORDER-QR-CODES-${size.label}`);
  }
  await page.setViewportSize(SIZES[0]);

  // ONLINE_ORDER-F02: the sheet, one card per table with its drawn QR, its number and its zone.
  await shown(page).locator(`[data-testid=${LIST}-print]`).click();
  await expect.poll(async () => (await printed()).count).toBe(1);
  const sheet = (await printed()).cards;
  for (const table of tables) {
    expect(sheet, `table ${table.number} on the sheet`).toContainEqual({ words: `Scan to order Table ${table.number} ${ZONE}`, drawn: true });
  }
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await expect(page.locator('body > .ep-print-root')).toHaveCount(0);

  // ONLINE_ORDER-F01: regenerating asks first, says the printed QR stops working, and gives a new code.
  await rowAction(page, LIST, first.id, 'regenerate');
  const confirm = page.locator('.ep-confirm-dialog').last();
  await expect(confirm).toContainText(`Regenerate the QR of table ${first.number} (${ZONE})?`);
  await expect(confirm).toContainText('stops working at once');
  await untilStill(page);
  await capture(page, 'ONLINE-ORDER-QR-CODES-regenerate-confirm');
  await confirm.getByRole('button', { name: 'Regenerate QR' }).click();
  await expect(toasts(page).last()).toContainText(`Table ${first.number} (${ZONE}) has a new QR`);
  const old = before.find((one) => one.table_id === first.id)!;
  await expect.poll(async () => (await codes()).find((one) => one.table_id === first.id)!.code).not.toBe(old.code);
  await expect(row(first.id)).not.toContainText(old.url!);
  expect((await codes()).find((one) => one.table_id === second.id)!.code).toBe(before.find((one) => one.table_id === second.id)!.code);

  // ONLINE_ORDER-F02: that table's new QR, alone.
  await rowAction(page, LIST, first.id, 'print');
  await expect.poll(async () => (await printed()).count).toBe(2);
  expect((await printed()).cards).toEqual([{ words: `Scan to order Table ${first.number} ${ZONE}`, drawn: true }]);
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
});

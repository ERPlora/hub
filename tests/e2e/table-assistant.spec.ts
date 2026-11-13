// The assistant's card for a write of Tables (base's half is hub#416, BASE-F97): the table it acts on with its zone
// (the number repeats across zones), the zone it goes to and the check a transfer moves, by the names the room's
// screens give them, never by the id the model sent, and never left out for whoever may read them. End to end with the
// stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded
// with it (README of this folder, «El asistente»). The owner asks, in Spanish, to take a table of the terrace to the
// dining room (TABLE-F04) and, in English, to transfer the check of that table to another one (TABLE-F15, dangerous):
// each card names them; cancelled, nothing changes. What this file creates carries `E2ETac` and goes away; the apps it
// turns on are turned off again.
// flow: table-assistant-card
// flow: TABLE-F04 TABLE-F15 BASE-F97
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { NOT_DONE } from './assistant-provider';
import { ask, cardSpec, ownerIn } from './assistant-card-helpers';
import { card, openPanel, panel } from './assistant-real';
import { A, api, capture, untilStill } from './helpers';
import { cleanRoom } from './sale-helpers';

const KEY = 'FIX-HUB-TABLE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
const TAG = 'E2ETac';
const TERRACE = `${TAG}Terraza`;
const ROOM = `${TAG}Comedor`;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
/** The apps a table needs, in the order they require each other: a business is born with every app off. */
const NEEDED = ['customer', 'tax', 'sale', 'table'];

type Table = { id: string; number: string; label: string; zone_id: string | null };
type Check = { id: string; label: string; table_id: string | null; order_id: string | null; status: string };

/** The room this file made, and the checks of Sales its seating opened. */
const cleanup = (): void => cleanRoom(TAG);

cardSpec(NEEDED, cleanup);

const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();

async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
}

/** The owner in `language`, with table 5 of the terrace and table 2 of the dining room made through Tables' API:
 *  `[context, page, the terrace, the dining room, table 5, table 2]`. */
async function ownerWithARoom(
  browser: Browser,
  language: 'es' | 'en',
): Promise<[BrowserContext, Page, string, string, Table, Table]> {
  const [context, page] = await ownerIn(browser, language);
  const zones: string[] = [];
  for (const name of [TERRACE, ROOM]) {
    const zone = await api<{ id: string }>(context, A, 'POST', '/table/zones', { name });
    expect(zone.status, JSON.stringify(zone.data)).toBe(201);
    zones.push(zone.data.id);
  }
  const tables: Table[] = [];
  for (const [zone_id, number] of [
    [zones[0], '5'],
    [zones[1], '2'],
  ]) {
    const table = await api<Table>(context, A, 'POST', '/table/tables', { zone_id, number });
    expect(table.status, JSON.stringify(table.data)).toBe(201);
    tables.push(table.data);
  }
  return [context, page, zones[0], zones[1], tables[0], tables[1]];
}

async function tableNow(context: BrowserContext, id: string): Promise<Table> {
  const read = await api<Table>(context, A, 'GET', `/table/tables/detail?id=${id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  return read.data;
}

test('table-assistant-card — in Spanish taking a table to another zone names the table with its zone and the zone it goes to, never by their ids', async ({ browser }) => {
  const [context, page, terrace, room, five] = await ownerWithARoom(browser, 'es');
  // The name the card says, as the room's screens say it: the number with its zone.
  expect(five.label).toBe(`5 (${TERRACE})`);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK table__table__update ${JSON.stringify({ id: five.id, move_to_zone_id: room })}`);
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Cambiar en Mesas: 5 (${TERRACE}) · ${ROOM}`);
    for (const id of [five.id, room]) await expect(card(page)).not.toContainText(id);
    await untilStill(page);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  expect((await tableNow(context, five.id)).zone_id).toBe(terrace);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

test('table-assistant-card — in English transferring a check names the check by its table and the table it goes to, never by their ids', async ({ browser }) => {
  const [context, page, , , five, two] = await ownerWithARoom(browser, 'en');
  const seated = await api<Check>(context, A, 'POST', '/table/sessions/open', { table_id: five.id, guests_count: 2 });
  expect(seated.status, JSON.stringify(seated.data)).toBe(201);
  expect(seated.data.label).toBe(`5 (${TERRACE})`);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK table__session__transfer ${JSON.stringify({ id: seated.data.id, to_table_id: two.id })}`);
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText(`5 (${TERRACE})`);
  await expect(card(page)).toContainText(`Destination table: 2 (${ROOM})`);
  for (const id of [seated.data.id, two.id]) await expect(card(page)).not.toContainText(id);
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText(NOT_DONE.en);
  const after = await api<Check>(context, A, 'GET', `/table/sessions/detail?id=${seated.data.id}`);
  expect([after.data.table_id, after.data.status]).toEqual([five.id, 'open']);
  await context.close();
});

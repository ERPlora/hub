// The assistant's card for a write of Tables (FIX-HUB-TABLE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's half is hub#416,
// BASE-F97): the table it acts on with its zone (the number repeats across zones), the zone it goes to and the check a
// transfer moves, by the names the room's screens give them, never by the id the model sent (and, since hub#416, never
// left out for whoever may read them). End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El
// asistente»). The owner asks, in Spanish, to take a table of the terrace to the dining room (TABLE-F04) and, in English,
// to transfer the check of that table to another one (TABLE-F15, dangerous): each card names them; cancelled, nothing
// changes. What this file creates carries `E2ETac` and goes away; the apps it turns on are turned off again.
// flow: table-assistant-card
// flow: TABLE-F04 TABLE-F15 BASE-F97
import { execSync } from 'node:child_process';

import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, compactBar, login, psql, REPO_DIR, shown, turnOn, untilStill } from './helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-TABLE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
const TAG = 'E2ETac';
const TERRACE = `${TAG}Terraza`;
const ROOM = `${TAG}Comedor`;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
/** The apps a table needs, in the order they require each other: a business is born with every app off. */
const NEEDED = ['customer', 'tax', 'sale', 'table'];
const TABLES = `select id from table_table where zone_id in (select id from table_zone where name like '${TAG}%')`;
const SESSIONS = `select id from table_tablesession where table_id in (${TABLES})`;

type Table = { id: string; number: string; label: string; zone_id: string | null };
type Check = { id: string; label: string; table_id: string | null; order_id: string | null; status: string };

let provider: Provider;
let wasOn = new Set<string>();

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** The room this file made, and the checks of Sales its seating opened (they carry no line nor any sale). */
function cleanup(): void {
  const orders = psql(`select order_id from table_tablesession where id in (${SESSIONS}) and order_id is not null`)
    .split('\n')
    .filter(Boolean)
    .map((id) => `'${id}'`)
    .join(', ');
  psql(
    [
      `delete from table_sessionmove where session_id in (${SESSIONS})`,
      `delete from table_tablesession where id in (${SESSIONS})`,
      `delete from table_hold where table_id in (${TABLES})`,
      ...(orders ? [`delete from sale_order where id in (${orders})`] : []),
      `delete from table_table where id in (${TABLES})`,
      `delete from table_zone where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const before = await api<{ apps: { id: string; state: string }[] }>(context, A, 'GET', '/apps');
  wasOn = new Set(before.data.apps.filter((app) => app.state === 'on').map((app) => app.id));
  await turnOn(context, A, ...NEEDED.filter((id) => !wasOn.has(id)));
  await context.close();
});

test.beforeEach(() => {
  // The month's assistant messages of the business `a` back to none: a run never spends the plan's allowance.
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
  cleanup();
});

test.afterAll(async ({ browser }) => {
  cleanup();
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  for (const app of [...NEEDED].reverse().filter((id) => !wasOn.has(id))) {
    const off = await api(context, A, 'POST', '/apps/disable', { app });
    expect(off.status, `turn off ${app}: ${JSON.stringify(off.data)}`).toBe(200);
  }
  await context.close();
  await provider?.close();
});

// ── The panel and its card (as base-assistant.spec.ts drives them) ──

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
}

async function openPanel(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
}

/** Writes `text` and sends it; resolves once its answer has started (its card is up before the turn ends). */
async function ask(page: Page, text: string): Promise<void> {
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
}

/** The owner in `language`, with table 5 of the terrace and table 2 of the dining room made through Tables' API:
 *  `[context, page, the terrace, the dining room, table 5, table 2]`. */
async function ownerWithARoom(
  browser: Browser,
  language: 'es' | 'en',
): Promise<[BrowserContext, Page, string, string, Table, Table]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
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
  // The e2e's provider answers a cancelled write in one language only (assistant-provider.ts).
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  const after = await api<Check>(context, A, 'GET', `/table/sessions/detail?id=${seated.data.id}`);
  expect([after.data.table_id, after.data.status]).toEqual([five.id, 'open']);
  await context.close();
});

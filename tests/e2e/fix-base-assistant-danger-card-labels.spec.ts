// The dangerous card of the assistant calls each datum by the title its app wrote for it
// (FIX-HUB-BASE-ASSISTANT-DANGER-CARD-CALLS-THE-RECORD-BY-ITS-FIELD-NAME, BASE-F97 step 2 and BASE-F98): transferring
// a check (TABLE-F15, dangerous) said «Registro: 5 (Terraza)», the card's own word for a datum named `id`, where
// Tables titles it «Cuenta». End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts,
// `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El asistente»). The owner asks,
// in Spanish, to transfer the check of table 5 of the terrace to table 2 of the dining room: the card says «Cuenta» and
// «Mesa de destino», never «Registro»; cancelled, nothing changes. A datum its app does not title keeps the card's word
// («Registro: Barra» when removing a device: base-assistant.spec.ts). What this file creates carries `E2EDcl` and goes
// away; the apps it turns on are turned off again.
// flow: base-assistant-danger-card-labels
// flow: BASE-F97 BASE-F98 TABLE-F15
import { execSync } from 'node:child_process';

import { expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, compactBar, exposeMovingInPage, login, psql, REPO_DIR, shown, turnOn, untilStill } from './helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-BASE-ASSISTANT-DANGER-CARD-CALLS-THE-RECORD-BY-ITS-FIELD-NAME';
const TAG = 'E2EDcl';
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

type Table = { id: string; label: string };
type Check = { id: string; label: string; table_id: string | null; status: string };

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

/** The dangerous card ready for its capture, as base-assistant.spec.ts waits for it: «Confirmación» focused, its
 *  label floated and nothing moving on the page, the label's move included, two frames apart. */
async function confirmationSettled(page: Page): Promise<boolean> {
  const field = card(page).locator('[data-testid="assistant-confirm-input"]');
  await expect(field).toHaveClass(/\bhas-focus\b/);
  await expect(field).toHaveClass(/\blabel-floating\b/);
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
  await untilStill(page);
  await exposeMovingInPage(page);
  return field.evaluate(async (input) => {
    const label = input.querySelector('.label-text-wrapper');
    const look = () =>
      label && `${JSON.stringify(label.getBoundingClientRect())} ${getComputedStyle(label).transform} ${getComputedStyle(label).opacity}`;
    const before = look();
    await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
    const moving = (window as unknown as { __movingInPage: () => string[] }).__movingInPage();
    return input.classList.contains('has-focus') && label !== null && look() === before && moving.length === 0;
  });
}

test('base-assistant-danger-card-labels — in Spanish transferring a check calls it «Cuenta», the title Tables gives it, never «Registro»', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const tables: Table[] = [];
  for (const [name, number] of [
    [TERRACE, '5'],
    [ROOM, '2'],
  ]) {
    const zone = await api<{ id: string }>(context, A, 'POST', '/table/zones', { name });
    expect(zone.status, JSON.stringify(zone.data)).toBe(201);
    const table = await api<Table>(context, A, 'POST', '/table/tables', { zone_id: zone.data.id, number });
    expect(table.status, JSON.stringify(table.data)).toBe(201);
    tables.push(table.data);
  }
  const [five, two] = tables;
  const seated = await api<Check>(context, A, 'POST', '/table/sessions/open', { table_id: five.id, guests_count: 2 });
  expect(seated.status, JSON.stringify(seated.data)).toBe(201);
  expect(seated.data.label).toBe(`5 (${TERRACE})`);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK table__session__transfer ${JSON.stringify({ id: seated.data.id, to_table_id: two.id })}`);
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Cuenta: 5 (${TERRACE})`);
    await expect(card(page)).toContainText(`Mesa de destino: 2 (${ROOM})`);
    await expect(card(page)).not.toContainText('Registro:');
    for (const id of [seated.data.id, two.id]) await expect(card(page)).not.toContainText(id);
    expect(await confirmationSettled(page), `${KEY}-${vp.label} caught before it settled`).toBe(true);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  const after = await api<Check>(context, A, 'GET', `/table/sessions/detail?id=${seated.data.id}`);
  expect([after.data.table_id, after.data.status]).toEqual([five.id, 'open']);
  // The session, for ui-clip-sweep.sh over the screen behind the card (its pages are behind the login).
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

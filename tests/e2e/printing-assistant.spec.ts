// The assistant's card for a write of Printing (FIX-HUB-PRINTING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's half is
// hub#416, BASE-F97): since hub#416 the card left out every id its schema does not mark, so «cambia las impresoras de la
// tablet del mostrador» or «reintenta el ticket» said no device, no printer and no job, and «imprime la comanda» said
// its document as the model sent it («kitchen_order»). Now each record is named as the Printing screens show it — a
// device and its printers by their names, a job as the queue titles it («Recibo …») —, read as the person, never by
// its id, and a document by the queue's word for it («Comanda de cocina»). End to end with the stack's SaaS gateway and
// the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this
// folder, «El asistente»). Cancelled, nothing changes. What this file creates carries its own prefix (E2E PAC) and goes
// away; the app it turns on is turned off again.
// flow: printing-assistant-card
// flow: PRINTING-F16 BASE-F97
import { execSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, compactBar, login, psql, REPO_DIR, shown, turnOn, untilStill } from './helpers';
import { forgetDevices } from './printing-helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-PRINTING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
/** An id as a schema's `format: uuid` takes it: never on a card. */
const AN_ID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
const NEEDED = ['printing'];
const PREFIX = 'E2E PAC';
const RUN = Date.now().toString(36).toUpperCase();
/** The document's number of the receipt this file queues: what the queue titles its job by. */
const NUMBER = `E2EPAC-${RUN}`;

let provider: Provider;
let wasOn = new Set<string>();

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** Deletes what this file created: its receipt's jobs, its device and its printers (`E2E PAC …`). */
function cleanUp(): void {
  psql(
    `delete from printing_printjob where reference like 'E2EPAC-%' or printer_id in (select id from printing_printer where name like '${PREFIX} %')`,
  );
  forgetDevices(`${PREFIX} %`, { names: [`${PREFIX} %`] });
  psql(`delete from printing_printer where name like '${PREFIX} %'`);
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
  cleanUp();
});

test.afterAll(async ({ browser }) => {
  cleanUp();
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

type SentCard = { fields: { name: string; kind: string; label: string; value: unknown }[] };

/** The card of the confirm frame of a turn's answer (`text/event-stream`: one `data: <JSON>` per frame), if any. */
function confirmedCard(stream: string): SentCard | undefined {
  const frames = stream
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => JSON.parse(line.slice(5)) as { type: string; card?: SentCard });
  return frames.find((frame) => frame.type === 'confirm')?.card;
}

/** The card the server sends for the person to confirm, as it arrives: the answer of the turn that carries it. */
async function sentCard(page: Page): Promise<SentCard> {
  const answer = await page.waitForResponse(
    async (response) => response.url().endsWith('/api/assistant/turn') && confirmedCard(await response.text()) !== undefined,
  );
  return confirmedCard(await answer.text())!;
}

const said = (sent: SentCard): Record<string, unknown> => Object.fromEntries(sent.fields.map((field) => [field.name, field.value]));

async function cancel(page: Page): Promise<void> {
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
}

async function made<T>(context: BrowserContext, path: string, body: unknown, headers: Record<string, string> = {}): Promise<T> {
  const host = new URL(A).hostname;
  const csrf = (await context.cookies(A)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const res = await context.request.post(`${A}/api${path}`, {
    headers: { 'X-CSRFToken': csrf, Accept: 'application/json', ...headers },
    data: body,
  });
  expect(res.status(), `${path}: ${await res.text()}`).toBe(201);
  return (await res.json()) as T;
}

type Printer = { id: string; name: string };

/** The owner, in Spanish, with the printers «E2E PAC Caja» and «E2E PAC Cocina», the device «E2E PAC Tablet del
 * mostrador» that reaches the till's, and a receipt in the queue: made through the app's own API. */
async function ownerWithAPrintingBusiness(browser: import('@playwright/test').Browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const printer = (name: string, usage: string, address: string) =>
    made<Printer>(context, '/printing/printers', { name: `${PREFIX} ${name} ${RUN}`, kind: 'network', address, usage });
  const till = await printer('Caja', 'receipt', '10.0.0.71');
  const kitchen = await printer('Cocina', 'kitchen', '10.0.0.72');
  const device = await made<{ id: string; name: string }>(
    context,
    '/printing/devices',
    { name: `${PREFIX} Tablet del mostrador ${RUN}`, printers: [till.id] },
    { 'X-Device-Id': randomUUID() },
  );
  const queued = await made<{ job: { id: string } }>(context, '/printing/jobs', {
    document_type: 'receipt',
    document: { receipt_id: NUMBER, items: [{ name: 'Corte', quantity: 1, total: 18 }], total: 18 },
    printer: till.id,
  });
  return { context, page, till, kitchen, device, job: queued.job };
}

test('printing-assistant-card — in Spanish changing a device’s printers, retrying a job and printing a kitchen order name the device, the printers, the job and the document, never by their id', async ({ browser }) => {
  const { context, page, till, kitchen, device, job } = await ownerWithAPrintingBusiness(browser);
  // The new reads answer over HTTP, as the card reads them.
  const read = await api<{ label: string }>(context, A, 'GET', `/printing/jobs/detail?job_id=${job.id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  expect(read.data.label).toBe(`Recibo ${NUMBER}`);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);

  // «Que la tablet del mostrador imprima también por la de cocina»: the device and its printers by their names, as the
  // server sends them and as the card says them, one after another (never «Impresoras: 2 elementos»).
  let sent = sentCard(page);
  await ask(page, `E2E-ASK printing__device__update ${JSON.stringify({ device_id: device.id, printers: [till.id, kitchen.id] })}`);
  await expect(card(page)).toBeVisible();
  let fields = await sent;
  expect(said(fields)).toEqual({ device_id: device.name, printers: [till.name, kitchen.name] });
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Dispositivo: ${device.name}`);
    await expect(card(page)).toContainText(`Impresoras: ${till.name}, ${kitchen.name}`);
    await expect(card(page)).not.toContainText('elementos');
    await expect(card(page)).not.toContainText(AN_ID);
    await untilStill(page);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await cancel(page);

  // «Reintenta el ticket»: the job as the queue titles it, by the queue's word for a job.
  sent = sentCard(page);
  await ask(page, `E2E-ASK printing__job__retry ${JSON.stringify({ job_id: job.id })}`);
  await expect(card(page)).toBeVisible();
  fields = await sent;
  expect(fields.fields.find((field) => field.name === 'job_id')).toMatchObject({ value: `Recibo ${NUMBER}`, label: 'Trabajo' });
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  await expect(card(page)).toContainText(`Recibo ${NUMBER}`);
  await expect(card(page)).not.toContainText(AN_ID);
  await cancel(page);

  // «Imprime la comanda de cocina»: the document by the queue's word, never «kitchen_order».
  sent = sentCard(page);
  await ask(page, `E2E-ASK printing__job__create ${JSON.stringify({ document_type: 'kitchen_order', document: { order_number: 'M-1' } })}`);
  await expect(card(page)).toBeVisible();
  expect(said(await sent).document_type).toBe('Comanda de cocina');
  await expect(card(page)).toContainText('Comanda de cocina');
  await expect(card(page)).not.toContainText('kitchen_order');
  await cancel(page);

  // Cancelled, nothing changed: the device still reaches the till's printer only, and the receipt still waits.
  const devices = await api<{ rows: { id: string; printers: { id: string }[] }[] }>(context, A, 'GET', '/printing/devices');
  expect(devices.data.rows.find((row) => row.id === device.id)?.printers.map((p) => p.id)).toEqual([till.id]);
  const still = await api<{ status: string; attempts: number }>(context, A, 'GET', `/printing/jobs/detail?job_id=${job.id}`);
  expect([still.data.status, still.data.attempts]).toEqual(['pending', 0]);
  const queue = await api<{ total: number }>(context, A, 'GET', '/printing/jobs?search=M-1');
  expect(queue.data.total).toBe(0);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

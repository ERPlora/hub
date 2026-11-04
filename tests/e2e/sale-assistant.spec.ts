// The card of a write of Sales the assistant wants to run (hub#561, FIX-HUB-SALE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS),
// end to end with its real dependencies: the Hub of this stack, its SaaS's gateway and the e2e's provider
// (assistant-provider.ts, its marker `E2E-ASK <tool> <JSON>`). The SaaS must be seeded with that provider (README «El
// asistente»). Since hub#416 a card leaves out every id its app does not name, so the person confirmed sending a round
// or deleting a section without reading which one. Now each record goes by the name Sales' screens give it, read as the
// person, never by its id, and the order type by Kitchen's word. Cancelled: nothing is sent nor deleted.
// What this file creates is deleted after it.
// flow: SALE-F20 SALE-F35 BASE-F97
import { execSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, compactBar, login, psql, REPO_DIR, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, stamp } from './sale-helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-SALE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
const RUN = stamp();
const VIEWPORTS = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1440', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
/** An id as a schema's `format: uuid` takes it: never on a card. */
const AN_ID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

let provider: Provider;
let product: Product;

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** The month's assistant messages of the business `a` back to none: a run never spends the plan's allowance. */
function unspend(): void {
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
}

test.beforeAll(async ({ browser }) => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  product = await createProduct(context, {
    name: `E2E Card ${RUN}`,
    sku: `E2E-CARD-${RUN}`,
    price: 1210,
    tax_category_key: 'product.generic',
  });
  await context.close();
});

test.afterAll(async () => {
  await provider?.close();
  try {
    cleanSales();
    cleanInventory();
    psql("delete from sale_department where name like 'e2e %'");
  } finally {
    unspend();
  }
});

test.beforeEach(() => {
  unspend();
});

// ── The assistant's panel (as base-assistant.spec.ts drives it) ──

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

async function openPanel(page: Page): Promise<void> {
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
}

/** Writes `text` and sends it with Enter, without waiting for the turn to end (a card stops it half-way). */
async function ask(page: Page, text: string): Promise<void> {
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
}

async function cancelCard(page: Page): Promise<void> {
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
}

type SentCard = { fields: { name: string; label: string; value: unknown }[] };

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

const saidBy = (sent: SentCard) => Object.fromEntries(sent.fields.map((field) => [field.name, [field.label, field.value]]));

/** The assistant asks for `tool` with `data`: what the card says, as sent and with its id nowhere. */
async function asked(page: Page, tool: string, data: Record<string, unknown>): Promise<Record<string, unknown[]>> {
  const sent = sentCard(page);
  await ask(page, `E2E-ASK ${tool} ${JSON.stringify(data)}`);
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  const fields = await sent;
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  await expect(card(page)).not.toContainText(AN_ID);
  return saidBy(fields) as Record<string, unknown[]>;
}

async function inSpanish(context: BrowserContext, page: Page, path: string): Promise<void> {
  await login(page, A, path);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${A}${path}`);
  await openPanel(page);
}

test('SALE-F20 — in Spanish sending a round names the check and the order type, and removing a line names the line, never by their ids', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await inSpanish(context, page, '/sale/pos');
    const label = `e2e Mesa ${RUN}`;
    const opened = await api<{ id: string; lines: { id: string }[] }>(context, A, 'POST', '/sale/orders', {
      label,
      lines: [{ product_id: product.id }],
    });
    expect(opened.status, JSON.stringify(opened.data)).toBe(201);
    const check = opened.data;

    expect(await asked(page, 'sale__order__fire', { order_id: check.id, channel: 'takeaway' })).toMatchObject({
      order_id: ['Cuenta abierta', label],
      channel: ['Tipo de pedido', 'Para llevar'],
    });
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(label);
      await expect(card(page)).toContainText('Para llevar');
      await untilStill(page);
      await capture(page, `${KEY}-fire-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancelCard(page);

    expect(await asked(page, 'sale__order__remove_line', { order_id: check.id, line_id: check.lines[0].id })).toMatchObject({
      order_id: ['Cuenta abierta', label],
      line_id: ['Línea', product.name],
    });
    await expect(card(page)).toContainText(product.name);
    await untilStill(page);
    await capture(page, `${KEY}-remove-line-1440`);
    await cancelCard(page);

    // Cancelled: the line stays on the check and nothing went to the kitchen.
    const after = await api<{ lines: { id: string }[] }>(context, A, 'GET', `/sale/orders/detail?order_id=${check.id}`);
    expect(after.status, JSON.stringify(after.data)).toBe(200);
    expect(after.data.lines.map((line) => line.id)).toEqual([check.lines[0].id]);
    expect(psql(`select count(*) from kitchen_ticket where order_id = '${check.id}'`)).toBe('0');
  } finally {
    await context.close();
  }
});

test('SALE-F35 — in Spanish deleting a section names it, as the Sections screen calls it, never by its id', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await inSpanish(context, page, '/sale/departments');
    const name = `e2e Frutas ${RUN}`;
    const section = await api<{ id: string }>(context, A, 'POST', '/sale/departments', { name, tax_category_key: 'product.generic' });
    expect(section.status, JSON.stringify(section.data)).toBe(201);

    expect(await asked(page, 'sale__department__delete', { id: section.data.id })).toMatchObject({ id: ['Sección', name] });
    // A normal write is one line, of values with no titles (`cardLine`, BASE-F97): the title goes in what the server sent.
    await expect(card(page)).toContainText(name);
    await untilStill(page);
    await capture(page, `${KEY}-section-1440`);
    await cancelCard(page);

    // Cancelled: the section is still there.
    expect(psql(`select count(*) from sale_department where id = '${section.data.id}' and not is_deleted`)).toBe('1');
  } finally {
    await context.close();
  }
});

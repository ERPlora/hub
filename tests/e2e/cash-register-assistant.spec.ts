// Closing the drawer by asking the assistant (CASH_REGISTER-F09; PLAN §30, the first of the «Cinco acciones de IA
// pulidas»: the cash count, with its summary before and its confirmation), end to end with its real dependencies: the
// Hub of this stack, its SaaS's gateway (`/internal/assistant/*`) and the e2e's provider (assistant-provider.ts, its
// marker `E2E-CLOSE-CASH <cents>`), which reads the close's summary, says it and asks for the close of that session.
// The SaaS must be seeded with that provider (README of this folder, «El asistente»).
// The owner, with a shift open and a cash sale in it, asks «cierra la caja con 250 € contados»: the summary comes
// first (session, counted, expected, difference), then the dangerous card; «Cancel» leaves the shift open, typing the
// word closes it and «Caja» shows it closed with its three amounts. The dangerous card carries, in «What will happen»,
// what closing gives: the session's number, its drawer, the expected cash and the difference, as money in the business's
// currency (FIX-HUB-CASH_REGISTER-ASSISTANT-CLOSE-CARD-WITHOUT-PREVIEW, through base's preview, BASE-F98), the
// difference with its sign as «Cash register» writes it, in English and in Spanish («+€137.90», «+137,90 €»: over at a
// glance; FIX-HUB-BASE-ASSISTANT-CARD-POSITIVE-DIFFERENCE-WITHOUT-SIGN, BASE-F97). A cashier with the blind count on
// gets the summary and the card without the expected nor the difference, and the model never received them.
// What this file creates is deleted after it (its sessions, its drawer, its sale and its product); the settings go back.
// flow: CASH_REGISTER-F09
// flow: CASH_REGISTER-F07
// flow: BASE-F97
import { execSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, compactBar, EMPLOYEE, login, psql, REPO_DIR, shot, shown, untilStill } from './helpers';
import { createProduct, type Product } from './inventory-helpers';
import { cleanDocumentsOf, stamp } from './sale-helpers';
import { STACK } from './stack';

const KEY = 'FIX-CASH_REGISTER-NO-VOICE-CLOSE-WITH-ASSISTANT';
const PREVIEW_KEY = 'FIX-HUB-CASH_REGISTER-ASSISTANT-CLOSE-CARD-WITHOUT-PREVIEW';
const SIGN_KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-POSITIVE-DIFFERENCE-WITHOUT-SIGN';
const RUN = stamp();
const SKU = `E2E-CRA-${RUN}`;
/** The drawer this file opens its shifts on: the card names it. */
const DRAWER = `E2E Barra ${RUN}`;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);

let provider: Provider;
let shirt: Product;
let drawerId = '';
/** Money as the card shows it to an English or a Spanish reader: the business's currency and decimals (base's
 *  `formatValue`). */
let cardMoney: (cents: number, locale?: string) => string;
/** The sessions this file opened: the only ones its cleanup deletes. */
const mine = new Set<string>();
const settingsBefore: Record<string, unknown> = {};

interface Current {
  session: { id: string; number: string; expected_balance: number | null } | null;
}
interface Currency {
  currency: string;
  decimals: number;
}
interface Detail {
  id: string;
  number: string;
  status: string;
  expected_balance: number | null;
  closing_balance: number | null;
  difference: number | null;
}

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

async function owner(browser: import('@playwright/test').Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/cash_register/sessions');
  return { context, page };
}

async function current(context: BrowserContext): Promise<Current> {
  return (await api<Current>(context, A, 'GET', '/cash_register/sessions/current')).data;
}

async function detailOf(context: BrowserContext, id: string): Promise<Detail> {
  return (await api<Detail>(context, A, 'GET', `/cash_register/sessions/detail?session_id=${id}`)).data;
}

async function settings(context: BrowserContext, values: Record<string, unknown>): Promise<void> {
  const saved = await api(context, A, 'POST', '/cash_register/settings', values);
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
}

/** One drawer open per business: a shift an earlier run left open is closed, at its expected. */
async function closeLeftOpen(context: BrowserContext): Promise<void> {
  const left = (await current(context)).session;
  if (!left) return;
  const closed = await api(context, A, 'POST', '/cash_register/sessions/close', {
    session_id: left.id,
    closing_balance: Math.max(left.expected_balance ?? 0, 0),
    closing_notes: 'e2e: left open by an earlier run',
  });
  expect(closed.status, JSON.stringify(closed.data)).toBe(200);
}

/** A shift open with `float` on this file's drawer and a 12.10 € shirt charged in cash through Sales. */
async function shiftWithACashSale(context: BrowserContext, float: number): Promise<Current['session'] & object> {
  await closeLeftOpen(context);
  const opened = await api<{ id: string; number: string }>(context, A, 'POST', '/cash_register/sessions/open', {
    opening_balance: float,
    register_id: drawerId,
  });
  expect(opened.status, JSON.stringify(opened.data)).toBe(201);
  mine.add(opened.data.id);
  const sale = await api(context, A, 'POST', '/sale/sales', {
    idempotency_key: `e2e-cra-${stamp()}`,
    lines: [{ product: shirt.sku, quantity: '1' }],
    payments: [{ method: 'cash' }],
  });
  expect(sale.status, JSON.stringify(sale.data)).toBe(201);
  return (await current(context)).session!;
}

test.beforeAll(async ({ browser }) => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  const { context } = await owner(browser);
  shirt = await createProduct(context, { name: `E2E Shirt ${RUN}`, sku: SKU, price: 1210, tax_category_key: 'product.generic' });
  const read = await api<Record<string, unknown>>(context, A, 'GET', '/cash_register/settings');
  for (const key of ['require_blind_count', 'require_closing_balance']) settingsBefore[key] = read.data[key];
  const drawer = await api<{ id: string }>(context, A, 'POST', '/cash_register/registers', { name: DRAWER });
  expect(drawer.status, JSON.stringify(drawer.data)).toBe(201);
  drawerId = drawer.data.id;
  const { currency, decimals } = (await api<Currency>(context, A, 'GET', '/cash_register/currency')).data;
  cardMoney = (cents, locale = 'en') =>
    new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      currencyDisplay: 'narrowSymbol',
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(cents / 10 ** decimals);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  await provider?.close();
  const { context } = await owner(browser);
  await closeLeftOpen(context);
  await api(context, A, 'POST', '/cash_register/settings', settingsBefore);
  await context.close();
  const ids = [...mine].map((id) => `'${id}'`).join(',');
  if (ids) {
    psql(`delete from cash_register_count where session_id in (${ids})`);
    psql(`delete from cash_register_movement where session_id in (${ids})`);
    psql(`delete from cash_register_session where id in (${ids})`);
  }
  // Its drawer goes too, unless a shift of another file was opened on it meanwhile (then it stays, inactive).
  if (drawerId) {
    psql(`update cash_register_register set is_active = false where id = '${drawerId}'`);
    psql(`delete from cash_register_register r where r.id = '${drawerId}' and not exists (select 1 from cash_register_session s where s.register_id = r.id)`);
  }
  cleanSaleAndProduct();
  unspend();
});

test.beforeEach(() => {
  unspend();
});

/** Deletes this run's sales (they sold its SKU) and its product. The fiscal documents Invoicing issued for those
 *  sales go first, with Invoicing's own cleanup. */
function cleanSaleAndProduct(): void {
  const orders = `select distinct order_id as id from sale_orderline where sku = '${SKU}'`;
  cleanDocumentsOf(orders);
  psql(
    [
      `create temp table cra_sales as select distinct sale_id as id from sale_saleline where sku = '${SKU}'`,
      `create temp table cra_orders as ${orders}`,
      `delete from printing_printjob where job_key like any (array(select 'sale-' || id || '-%' from cra_sales))`,
      'delete from sale_orderline where order_id in (select id from cra_orders) or sale_id in (select id from cra_sales)',
      'delete from sale_salepayment where sale_id in (select id from cra_sales)',
      'delete from sale_saleline where sale_id in (select id from cra_sales)',
      'delete from sale_sale where id in (select id from cra_sales)',
      'delete from sale_order where id in (select id from cra_orders)',
      `delete from inventory_stockmovement where product_id in (select id from inventory_product where sku = '${SKU}')`,
      `delete from inventory_productcategory where product_id in (select id from inventory_product where sku = '${SKU}')`,
      `delete from inventory_product where sku = '${SKU}'`,
    ].join('; '),
  );
}

// ── The assistant's panel (as base-assistant.spec.ts drives it) ──

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
const receipts = (page: Page): Locator => panel(page).locator('[data-testid="assistant-receipt"]');
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const previewBlock = (page: Page): Locator => card(page).locator('[data-testid="assistant-confirm-preview"]');
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

async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
}

/** What the model was told of the close's summary: the last tool result the gateway sent the provider, as sent. */
function toldSummary(): { raw: string; summary: Record<string, unknown> } {
  const chat = provider.seen.filter((seen) => seen.path === '/v1/chat/completions').at(-1)?.body;
  const messages = (chat?.messages ?? []) as { role: string; content?: unknown }[];
  const raw = String(messages.filter((message) => message.role === 'tool').at(-1)?.content ?? '');
  return { raw, summary: JSON.parse(raw || '{}') as Record<string, unknown> };
}

const euros = (cents: number) => `${(cents / 100).toFixed(2)} €`;

test('CASH_REGISTER-F09 — «close the drawer with 250 € counted»: the summary first, then the dangerous card; «Cancel» leaves it open, the typed word closes it', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/cash_register/sessions');
  const context = page.context();
  const shift = await shiftWithACashSale(context, 10000);
  const expected = 10000 + 1210;
  expect(shift.expected_balance).toBe(expected);

  await openPanel(page);
  await ask(page, 'E2E-CLOSE-CASH 25000 cierra la caja con 250 € contados');
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  // The summary, before the card: the session, the counted cash, the expected and the difference.
  const summary = lastAnswer(page);
  await expect(summary.locator('strong').first()).toHaveText(shift.number);
  await expect(summary).toContainText(`Contado: ${euros(25000)}`);
  await expect(summary).toContainText(`Esperado: ${euros(expected)}`);
  await expect(summary).toContainText(`Diferencia: +${euros(25000 - expected)}`);
  // The summary was the Hub's own reading, sent to the model as it is: never a figure the model made up.
  expect(toldSummary().summary).toMatchObject({ number: shift.number, closing_balance: 25000, expected_balance: expected });
  // The read never says it closed anything; the card is the dangerous one, naming the session and the count.
  await expect(receipts(page).filter({ hasText: 'Close in Cash register' })).toHaveCount(0);
  await expect(card(page)).toContainText('Close in Cash register. Check each datum before going on.');
  await expect(card(page)).toContainText(`Session: ${shift.number}`);
  await expect(card(page)).toContainText('Counted cash: €250.00');
  // And what closing gives (the close's summary, read as the owner): the session, its drawer, the expected and the
  // difference, as money in the business's currency, the difference over with its «+» as «Cash register» writes it;
  // the counted cash is not repeated.
  const willHappen = [
    `Session: ${shift.number}`,
    `Drawer: ${DRAWER}`,
    `Expected in the drawer: ${cardMoney(expected)}`,
    `Difference: +${cardMoney(25000 - expected)}`,
  ];
  const submit = card(page).locator('[data-testid="assistant-confirm-submit"] button');
  await expect(submit).toBeDisabled();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toBeVisible();
    await expect(previewBlock(page)).toContainText('What will happen');
    await expect(previewBlock(page).locator('li')).toHaveText(willHappen);
    // Each line wraps inside the card, never past it (390 wide).
    expect(await previewBlock(page).evaluate((el) => el.scrollWidth <= el.clientWidth), `${PREVIEW_KEY}-${vp.label} overflows`).toBe(true);
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${vp.label}`) });
    await page.screenshot({ path: shot(`${PREVIEW_KEY}-${vp.label}`) });
    await page.screenshot({ path: shot(`${SIGN_KEY}-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // «Cancel»: nothing closes.
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  await expect(receipts(page).last()).toContainText('Not done, cancelled: Close in Cash register');
  expect((await detailOf(context, shift.id)).status).toBe('open');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await openPanel(page);
    await summary.scrollIntoViewIfNeeded();
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-summary-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // Asked again, the word typed: it closes, as the person, with the three amounts frozen.
  await ask(page, 'E2E-CLOSE-CASH 25000 cierra la caja con 250 € contados');
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  await expect(previewBlock(page).locator('li')).toHaveText(willHappen);
  await card(page).locator('[data-testid="assistant-confirm-input"] input').fill('confirm');
  await expect(submit).toBeEnabled();
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText('Hecho.');
  await expect(receipts(page).last()).toContainText('Done: Close in Cash register');
  const closed = await detailOf(context, shift.id);
  expect([closed.status, closed.expected_balance, closed.closing_balance, closed.difference]).toEqual([
    'closed',
    expected,
    25000,
    25000 - expected,
  ]);

  // «Cash register» shows it closed, with its expected, counted and difference (the panel stays docked beside it).
  await page.goto(`${A}/cash_register/sessions`);
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  const row = shown(page).locator(`[data-testid=cash-register-sessions-row][data-id="${shift.id}"]`);
  await expect(row).toContainText('Closed');
  await expect(row).toContainText(/112\.10/);
  await expect(row).toContainText(/250\.00/);
  await expect(row).toContainText(/137\.90/);
  await expect(shown(page).locator('[data-testid=cash-register-new-session]')).not.toHaveAttribute('aria-disabled', 'true');
  // The owner's session, with the assistant docked, for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`).
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
});

test('BASE-F97 — in Spanish, the close card writes the difference over with its «+», as «Cash register» does', async ({ browser }) => {
  const { context, page } = await owner(browser);
  // In Spanish (the Hub's language cookie, as the sign-in sets it).
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const shift = await shiftWithACashSale(context, 10000);
  const expected = 10000 + 1210;
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${A}/cash_register/sessions`);
  await openPanel(page);
  await ask(page, 'E2E-CLOSE-CASH 25000 cierra la caja con 250 € contados');
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  const willHappen = [
    `Sesión: ${shift.number}`,
    `Cajón: ${DRAWER}`,
    `Esperado en el cajón: ${cardMoney(expected, 'es')}`,
    `Diferencia: +${cardMoney(25000 - expected, 'es')}`,
  ];
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toBeVisible();
    await expect(previewBlock(page)).toContainText('Lo que va a pasar');
    await expect(previewBlock(page).locator('li')).toHaveText(willHappen);
    expect(await previewBlock(page).evaluate((el) => el.scrollWidth <= el.clientWidth), `${SIGN_KEY}-es-${vp.label} overflows`).toBe(true);
    await untilStill(page);
    await page.screenshot({ path: shot(`${SIGN_KEY}-es-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'cancel');
  expect((await detailOf(context, shift.id)).status).toBe('open');
  await context.close();
});

test('CASH_REGISTER-F07 — with the blind count on, a cashier asking to close gets the summary without the expected nor the difference, and the model never gets them', async ({ browser }) => {
  const boss = await owner(browser);
  await settings(boss.context, { require_blind_count: true });
  const shift = await shiftWithACashSale(boss.context, 10000);
  const expected = 10000 + 1210;

  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/cash_register/sessions', EMPLOYEE);
  await openPanel(page);
  await ask(page, 'E2E-CLOSE-CASH 25000 cierra la caja con 250 € contados');
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  const summary = lastAnswer(page);
  await expect(summary.locator('strong').first()).toHaveText(shift.number);
  await expect(summary).toContainText(`Contado: ${euros(25000)}`);
  await expect(summary).toContainText('Arqueo ciego');
  await expect(summary).not.toContainText('Esperado');
  await expect(summary).not.toContainText('Diferencia');
  // Not even the model got them: the summary sent to it carries neither.
  const told = toldSummary();
  expect(told.summary).toMatchObject({ number: shift.number, closing_balance: 25000, expected_balance: null, difference: null, expected_hidden: true });
  expect(told.raw).not.toContain(String(expected));
  await expect(card(page)).toContainText('Counted cash: €250.00');
  // Nor does the card: what will happen names the session and its drawer, never the expected nor the difference.
  await expect(previewBlock(page).locator('li')).toHaveText([`Session: ${shift.number}`, `Drawer: ${DRAWER}`]);
  await expect(card(page)).not.toContainText('Expected');
  await expect(card(page)).not.toContainText('Difference');
  await expect(card(page)).not.toContainText(cardMoney(expected));
  await page.screenshot({ path: shot(`${KEY}-blind-1440`) });
  await page.screenshot({ path: shot(`${PREVIEW_KEY}-blind-1440`) });
  await decide(page, 'cancel');
  expect((await detailOf(boss.context, shift.id)).status).toBe('open');
  await context.close();
  await settings(boss.context, { require_blind_count: settingsBefore.require_blind_count ?? false });
  await boss.context.close();
});

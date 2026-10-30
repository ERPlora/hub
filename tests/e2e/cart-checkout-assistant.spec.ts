// The assistant's card for a write of Cart & checkout (FIX-HUB-CART_CHECKOUT-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's
// half is hub#416, BASE-F97): the cart a write acts on by its session code, as the Carts list and «Delete the cart …?»
// name it; a line by its product; an order by its number, as the Orders list — never by the id the model sent (and,
// since hub#416, never left out for whoever may read them). End to end with the stack's SaaS gateway and the e2e's
// provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder,
// «El asistente»). The owner, in Spanish, asks to empty a cart (CART_CHECKOUT-F04), to remove one of its lines
// (CART_CHECKOUT-F03) and to mark its order paid (CART_CHECKOUT-F09, dangerous): each card names its record; cancelled,
// nothing changes. What this file creates carries the session prefix of the cart_checkout specs and goes away; the app
// it turns on is turned off again. Each card says what its write does (FIX-HUB-BASE-ASSISTANT-CARD-SAYS-REMOVE-FOR-
// EMPTYING-A-CART, BASE-F97): emptying a cart «Vaciar», never «Quitar», the verb of removing one of its lines.
// flow: cart-checkout-assistant-card
// flow: base-assistant-card-verbs
// flow: CART_CHECKOUT-F03 CART_CHECKOUT-F04 CART_CHECKOUT-F09 BASE-F97
// flow: base-assistant-money-mark
import { execSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { type Cart, cleanUp, code, get, type Line, type Order, post } from './cart-checkout-helpers';
import { A, api, capture, compactBar, exposeMovingInPage, login, REPO_DIR, shot, shown, turnOn, untilStill } from './helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-CART_CHECKOUT-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
/** The captures of the verb of emptying a cart (base-assistant-card-verbs). */
const VERB_KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-SAYS-REMOVE-FOR-EMPTYING-A-CART';
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
/** The app the writes need: a business is born with every app off. */
const NEEDED = ['cart_checkout'];
/** The products of the cart, as the person would say them. */
const SHAMPOO = 'Champú de argán';
const MASK = 'Mascarilla nutritiva';

type Detail = Cart & { items: (Line & { product_name: string })[] };

let provider: Provider;
let wasOn = new Set<string>();

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
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

/** The dangerous card ready for its capture: «Confirmation» focused, its label floated, then one frame for the label's
 *  move to start, so `untilStill` waits for it (base-assistant.spec.ts). */
async function confirmationReady(page: Page): Promise<void> {
  const field = card(page).locator('[data-testid="assistant-confirm-input"]');
  await expect(field).toHaveClass(/\bhas-focus\b/);
  await expect(field).toHaveClass(/\blabel-floating\b/);
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
}

/** «Confirmation» as its capture must show it: focused, its label floated and, in the same frame, nothing moving on the
 *  page, the label's move included (base-assistant.spec.ts, rv-ui-35). */
async function confirmationSettled(page: Page): Promise<boolean> {
  await exposeMovingInPage(page);
  return card(page)
    .locator('[data-testid="assistant-confirm-input"]')
    .evaluate(async (field) => {
      const label = field.querySelector('.label-text-wrapper');
      const look = () =>
        label && `${JSON.stringify(label.getBoundingClientRect())} ${getComputedStyle(label).transform} ${getComputedStyle(label).opacity}`;
      const before = look();
      await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
      const moving = (window as unknown as { __movingInPage: () => string[] }).__movingInPage();
      return (
        field.classList.contains('has-focus') &&
        field.classList.contains('label-floating') &&
        label !== null &&
        look() === before &&
        moving.length === 0
      );
    });
}

/** The owner, in Spanish, with a cart of two lines made through the app's API: `[context, page, the cart, its lines]`. */
async function ownerWithACart(browser: import('@playwright/test').Browser): Promise<[BrowserContext, Page, Cart, Line[]]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const cart = await post<Cart>(context, '/cart_checkout/carts', { session_token: code('assistant') }, 201);
  const lines: Line[] = [];
  for (const [ref, name] of [['p-1', SHAMPOO], ['p-2', MASK]]) {
    const added = await post<{ item: Line }>(
      context,
      '/cart_checkout/items',
      { cart_id: cart.id, product_ref: ref, product_name: name, quantity: '1', unit_price: 1250 },
      201,
    );
    lines.push(added.item);
  }
  return [context, page, cart, lines];
}

const detail = (context: BrowserContext, cart: Cart): Promise<Detail> =>
  get<Detail>(context, `/cart_checkout/carts/detail?cart_id=${cart.id}`);

test('cart-checkout-assistant-card, base-assistant-card-verbs — in Spanish emptying a cart says «Vaciar» and names it by its session code, never by its id', async ({ browser }) => {
  const [context, page, cart] = await ownerWithACart(browser);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK cart_checkout__cart__clear ${JSON.stringify({ cart_id: cart.id })}`);
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Vaciar en Carrito y pago: ${cart.session_token}`);
    await expect(card(page)).not.toContainText('Quitar');
    await expect(card(page)).not.toContainText(cart.id);
    await untilStill(page);
    writeFileSync(shot(`${VERB_KEY}-${vp.label}`), await capture(page, `${KEY}-${vp.label}`));
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  expect((await detail(context, cart)).items.map((item) => item.product_name)).toEqual([SHAMPOO, MASK]);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

test('cart-checkout-assistant-card, base-assistant-card-verbs — in Spanish removing a line says «Quitar» and names it by its product, never by its id', async ({ browser }) => {
  const [context, page, cart, [, mask]] = await ownerWithACart(browser);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK cart_checkout__item__remove ${JSON.stringify({ item_id: mask.id })}`);
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText(`Quitar en Carrito y pago: ${MASK}`);
  await expect(card(page)).not.toContainText(mask.id);
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  expect((await detail(context, cart)).items.map((item) => item.product_name)).toEqual([SHAMPOO, MASK]);
  await context.close();
});

test('cart-checkout-assistant-card — in Spanish marking an order paid names it by its number, never by its id', async ({ browser }) => {
  const [context, page, cart] = await ownerWithACart(browser);
  const order = await post<Order>(
    context,
    '/cart_checkout/checkout/initiate',
    { cart_id: cart.id, customer_email: 'ana@example.com' },
    201,
  );
  expect(order.order_number).toMatch(/^OS-\d{8}-\d{4}$/);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK cart_checkout__order__mark_paid ${JSON.stringify({ order_id: order.id })}`);
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Pedido: ${order.order_number}`);
    await expect(card(page)).not.toContainText(order.id);
    await confirmationReady(page);
    await untilStill(page);
    expect(await confirmationSettled(page), `${KEY}-order-${vp.label} caught before it settled`).toBe(true);
    await capture(page, `${KEY}-order-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  const after = await get<Order>(context, `/cart_checkout/orders/detail?order_id=${order.id}`);
  expect(after.status).toBe('initiated');
  await context.close();
});

type SentCard = { fields: { name: string; kind: string; value: unknown; money?: unknown }[] };

/** The card of the confirm frame of a turn's answer (`text/event-stream`: one `data: <JSON>` per frame), if any. */
function confirmedCard(stream: string): SentCard | undefined {
  const frames = stream
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => JSON.parse(line.slice(5)) as { type: string; card?: SentCard });
  return frames.find((frame) => frame.type === 'confirm')?.card;
}

/** The card the server sends for the person to confirm, as it arrives: the answer of the turn that carries it (the
 *  first one only asks for the tool). */
async function sentCard(page: Page): Promise<SentCard> {
  const answer = await page.waitForResponse(
    async (response) => response.url().endsWith('/api/assistant/turn') && confirmedCard(await response.text()) !== undefined,
  );
  return confirmedCard(await answer.text())!;
}

// flow: base-assistant-money-mark (BASE-F97)
// FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS: a line added to a cart in dollars went as «12,50 €»: the
// write names the cart, not its currency. The card reads the cart as the person and sends the price in its currency,
// with its decimals (none in yen), as Shopify or Stripe show it. A normal card says its first three data in one line and
// the price is the sixth: the screen that shows every datum (an automation's question, FLOW-F29) gets it from what the
// server sends, checked here as it arrives. Cancelled: nothing is added.
test('base-assistant-money-mark — in Spanish a line added to a cart in another currency carries its price in it', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const dollars = await post<Cart>(context, '/cart_checkout/carts', { session_token: code('usd'), currency: 'USD' }, 201);
  const yen = await post<Cart>(context, '/cart_checkout/carts', { session_token: code('jpy'), currency: 'JPY' }, 201);
  const line = { product_ref: 'p-3', product_name: MASK, quantity: '1', unit_price: 1250 };
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  for (const [cart, money] of [
    [dollars, { currency: 'USD', decimals: 2 }],
    [yen, { currency: 'JPY', decimals: 0 }],
  ] as const) {
    const sent = sentCard(page);
    await ask(page, `E2E-ASK cart_checkout__item__add ${JSON.stringify({ cart_id: cart.id, ...line })}`);
    await expect(card(page)).toBeVisible();
    await expect(card(page)).toContainText(`Añadir en Carrito y pago: ${cart.session_token}`);
    expect((await sent).fields.find((field) => field.name === 'unit_price')).toMatchObject({ kind: 'money', value: 1250, money });
    await decide(page, 'cancel');
    await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  }
  for (const cart of [dollars, yen]) expect((await detail(context, cart)).items).toEqual([]);
  await context.close();
});

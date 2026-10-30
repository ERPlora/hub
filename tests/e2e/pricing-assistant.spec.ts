// The assistant's card for a change of a price of Price lists (FIX-HUB-PRICING-PRICE-UPDATE-CARD-IN-THE-BUSINESS-CURRENCY;
// base's half is hub#445, BASE-F97): «pon el champú a 15 en la lista de dólares» names the price by its id, and the card
// said it in the business's currency («15,00 €») for a list in dollars. The card reads the price as the person
// (`pricing.price_item.get`, with its list's currency) and says it in dollars, «15,00 $», with that currency's decimals,
// as Shopify or Stripe show an amount. End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El
// asistente»). Cancelled, the price stays as it was. What this file creates carries its own prefix (E2EPAS) and goes
// away; the apps it turns on are turned off again.
// FIX-HUB-PRICING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS: since hub#416 the card left out every id its schema does not
// mark, so «pon el champú a 15 en la lista de dólares» or «sube al 15 % la regla de verano» said no list, no product and
// no rule. Now each record is named as the Price lists screens show it, read as the person, never by its id.
// flow: pricing-assistant-price-currency
// flow: pricing-assistant-card-references
// flow: PRICING-F07 PRICING-F08 PRICING-F11 BASE-F97
import { execSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, compactBar, login, psql, REPO_DIR, shown, turnOn, untilStill } from './helpers';
import { createProduct, post, stamp } from './pricing-helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-PRICING-PRICE-UPDATE-CARD-IN-THE-BUSINESS-CURRENCY';
const REFERENCES_KEY = 'FIX-HUB-PRICING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
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
/** The apps the price needs: a business is born with every app off. */
const NEEDED = ['inventory', 'customer', 'pricing'];
const PREFIX = 'E2EPAS';
const RUN = stamp();
/** «15,00 $» as Spanish writes dollars (the symbol after, a space between, maybe a narrow one). */
const FIFTEEN_DOLLARS = /15,00\s\$/;

type PriceItem = { id: string; price: number; currency: string };

let provider: Provider;
let wasOn = new Set<string>();

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** Deletes what this file created (codes and SKUs `E2EPAS…`). */
function cleanUp(): void {
  const products = `select id from inventory_product where sku like '${PREFIX}-%'`;
  const lists = `select id from pricing_pricelist where code like '${PREFIX}%'`;
  psql(
    [
      `delete from pricing_priceitem where price_list_id in (${lists}) or product_id in (${products})`,
      `delete from pricing_pricelist where code like '${PREFIX}%'`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      `delete from inventory_product where sku like '${PREFIX}-%'`,
      `delete from pricing_discountrule where code like '${PREFIX}%'`,
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

type SentCard = { fields: { name: string; kind: string; value: unknown; money?: unknown }[] };

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

/** The owner, in Spanish, with the shampoo at 12,00 $ in a list in dollars, made through the apps' own API. */
async function ownerWithAPriceInDollars(browser: import('@playwright/test').Browser): Promise<[BrowserContext, Page, PriceItem]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const list = await post<{ id: string }>(context, '/pricing/price_lists', {
    code: `${PREFIX}${RUN}`,
    name: `E2E Pricing dólares ${RUN}`,
    currency: 'USD',
  });
  const product = await createProduct(context, `E2E Pricing champú ${RUN}`, `${PREFIX}-${RUN}`, 1500);
  const item = await post<PriceItem>(context, '/pricing/price_items', {
    price_list_id: list.id,
    product_id: product.id,
    price: 1200,
  });
  return [context, page, item];
}

const priceNow = async (context: BrowserContext, item: PriceItem): Promise<PriceItem> => {
  const read = await api<PriceItem>(context, A, 'GET', `/pricing/price_items/detail?id=${item.id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  return read.data;
};

test('pricing-assistant-price-currency — in Spanish changing a price of a list in dollars says it in dollars, never in the business’s', async ({ browser }) => {
  const [context, page, item] = await ownerWithAPriceInDollars(browser);
  // The new read answers the price's own currency over HTTP, as the card reads it.
  expect(await priceNow(context, item)).toMatchObject({ price: 1200, currency: 'USD' });
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  const sent = sentCard(page);
  await ask(page, `E2E-ASK pricing__price_item__update ${JSON.stringify({ id: item.id, price: 1500 })}`);
  await expect(card(page)).toBeVisible();
  // As the server sends it: an amount in the minor unit of the list's currency, with its decimals.
  expect((await sent).fields.find((field) => field.name === 'price')).toMatchObject({
    kind: 'money',
    value: 1500,
    money: { currency: 'USD', decimals: 2 },
  });
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(FIFTEEN_DOLLARS);
    await expect(card(page)).not.toContainText('€');
    await expect(card(page)).not.toContainText('1500');
    await untilStill(page);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  expect((await priceNow(context, item)).price).toBe(1200);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});


test('pricing-assistant-card-references — in Spanish adding a price names its list and its product, and changing a rule names the rule, never by their id', async ({ browser }) => {
  const [context, page] = await ownerWithAPriceInDollars(browser);
  const list = `E2E Pricing dólares ${RUN}`;
  const gel = `E2E Pricing gel ${RUN}`;
  const product = await createProduct(context, gel, `${PREFIX}-${RUN}-G`, 900);
  const rule = await post<{ id: string; name: string }>(context, '/pricing/rules', {
    code: `${PREFIX}${RUN}R`,
    name: `E2E Pricing verano ${RUN}`,
    rule_type: 'percent',
    percent: '10',
  });
  const [listId] = (await api<{ rows: { id: string }[] }>(context, A, 'GET', `/pricing/price_lists?code=${PREFIX}${RUN}`)).data.rows.map(
    (row) => row.id,
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);

  // «Pon el gel a 15 en la lista de dólares»: the list and the product by their names.
  let sent = sentCard(page);
  await ask(page, `E2E-ASK pricing__price_item__add ${JSON.stringify({ price_list_id: listId, product_id: product.id, price: 1500 })}`);
  await expect(card(page)).toBeVisible();
  let fields = (await sent).fields;
  expect(Object.fromEntries(fields.map((field) => [field.name, field.value]))).toMatchObject({
    price_list_id: list,
    product_id: gel,
  });
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Tarifa');
    await expect(card(page)).toContainText(list);
    await expect(card(page)).toContainText(gel);
    await expect(card(page)).toContainText(FIFTEEN_DOLLARS);
    await expect(card(page)).not.toContainText(AN_ID);
    await untilStill(page);
    await capture(page, `${REFERENCES_KEY}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');

  // «Sube al 15 % la regla de verano»: the rule by its name, titled as the rules' table, never «Registro».
  sent = sentCard(page);
  await ask(page, `E2E-ASK pricing__rule__update ${JSON.stringify({ id: rule.id, percent: '15' })}`);
  await expect(card(page)).toBeVisible();
  fields = (await sent).fields;
  expect(fields.find((field) => field.name === 'id')).toMatchObject({ value: rule.name, label: 'Regla de descuento' });
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  await expect(card(page)).toContainText('Regla de descuento');
  await expect(card(page)).toContainText(rule.name);
  await expect(card(page)).not.toContainText('Registro');
  await expect(card(page)).not.toContainText(AN_ID);
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
  // Cancelled, nothing changed: no price of the gel, and the rule still at 10 %.
  const prices = await api<{ total: number }>(context, A, 'GET', `/pricing/price_items?product_id=${product.id}`);
  expect(prices.data.total).toBe(0);
  const read = await api<{ percent: string }>(context, A, 'GET', `/pricing/rules/detail?id=${rule.id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  expect(Number(read.data.percent)).toBe(10);
  await context.close();
});

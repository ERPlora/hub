// The assistant's card for a change of a price of Price lists (base's half is hub#445, BASE-F97): «pon el champú a 15
// en la lista de dólares» names the price by its id, and the card must not say it in the business's currency
// («15,00 €») for a list in dollars. The card reads the price as the person
// (`pricing.price_item.get`, with its list's currency) and says it in dollars, «15,00 $», with that currency's decimals,
// as Shopify or Stripe show an amount. End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El
// asistente»). Cancelled, the price stays as it was. What this file creates carries its own prefix (E2EPAS) and goes
// away; the apps it turns on are turned off again.
// The card names every record the write touches, as the Price lists screens show it and read as the person, never by
// its id: «pon el gel a 15 en la lista de dólares» or «desactiva la regla de verano» say the list, the product and the
// rule, also the ids its schema does not mark (hub#416).
// flow: pricing-assistant-price-currency
// flow: pricing-assistant-card-references
// flow: PRICING-F07 PRICING-F08 PRICING-F12 BASE-F97

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { AN_ID, cardSpec } from './assistant-card-helpers';
import { askForACard, askForAPriceInDollars, cancelAtComputerSize, cancelInSpanish, card, openPanelAtTheDesk, sentCard } from './assistant-panel';
import { A, api, capture, login, psql, THREE_SIZES as VIEWPORTS, untilStill } from './helpers';
import { createProduct, post, stamp } from './pricing-helpers';

const KEY = 'FIX-HUB-PRICING-PRICE-UPDATE-CARD-IN-THE-BUSINESS-CURRENCY';
const REFERENCES_KEY = 'FIX-HUB-PRICING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
/** The apps the price needs: a business is born with every app off. */
const NEEDED = ['inventory', 'customer', 'pricing'];
const PREFIX = 'E2EPAS';
const RUN = stamp();
/** «15,00 $» as Spanish writes dollars (the symbol after, a space between, maybe a narrow one). */
const FIFTEEN_DOLLARS = /15,00\s\$/;

type PriceItem = { id: string; price: number; currency: string };


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

cardSpec(NEEDED, cleanUp);

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
  await openPanelAtTheDesk(page);
  // As the server sends it: an amount in the minor unit of the list's currency, with its decimals.
  await askForAPriceInDollars(page, 'pricing__price_item__update', { id: item.id, price: 1500 });
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(FIFTEEN_DOLLARS);
    await expect(card(page)).not.toContainText('€');
    // As a number of its own: the names on the card carry this run's stamp, which may spell it (hub#796).
    await expect(card(page)).not.toContainText(/\b1500\b/);
    await untilStill(page);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  expect((await priceNow(context, item)).price).toBe(1200);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});


test('pricing-assistant-card-references — in Spanish adding a price names its list and its product, and deactivating a rule names the rule, never by their id', async ({ browser }) => {
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
  await openPanelAtTheDesk(page);

  // «Pon el gel a 15 en la lista de dólares»: the list and the product by their names.
  let sent = sentCard(page);
  await askForACard(page, `E2E-ASK pricing__price_item__add ${JSON.stringify({ price_list_id: listId, product_id: product.id, price: 1500 })}`);
  let fields = (await sent).fields;
  expect(Object.fromEntries(fields.map((field) => [field.name, field.value]))).toMatchObject({
    price_list_id: list,
    product_id: gel,
  });
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(list);
    await expect(card(page)).toContainText(gel);
    await expect(card(page)).toContainText(FIFTEEN_DOLLARS);
    await expect(card(page)).not.toContainText(AN_ID);
    await untilStill(page);
    await capture(page, `${REFERENCES_KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);

  // «Desactiva la regla de verano», a dangerous write: its card lists each datum by its title, the rule by the rules'
  // own word and its name, never «Registro» nor its id.
  sent = sentCard(page);
  await askForACard(page, `E2E-ASK pricing__rule__deactivate ${JSON.stringify({ id: rule.id })}`);
  fields = (await sent).fields;
  expect(fields.find((field) => field.name === 'id')).toMatchObject({ value: rule.name, label: 'Regla de descuento' });
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  await expect(card(page)).toContainText(`Regla de descuento: ${rule.name}`);
  await expect(card(page)).not.toContainText('Registro');
  await expect(card(page)).not.toContainText(AN_ID);
  await cancelInSpanish(page);
  // Cancelled, nothing changed: no price of the gel, and the rule still on.
  const prices = await api<{ total: number }>(context, A, 'GET', `/pricing/price_items?product_id=${product.id}`);
  expect(prices.data.total).toBe(0);
  const read = await api<{ is_active: boolean }>(context, A, 'GET', `/pricing/rules/detail?id=${rule.id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  expect(read.data.is_active).toBe(true);
  await context.close();
});

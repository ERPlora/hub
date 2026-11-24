// The card of a write of Sales the assistant wants to run (hub#561), end to end with its real dependencies: the Hub of
// this stack, its SaaS's gateway and the e2e's provider (assistant-provider.ts, its marker `E2E-ASK <tool> <JSON>`).
// The SaaS must be seeded with that provider (README «El asistente»). The person must read which round is sent or which
// section is deleted before confirming, also when the app does not name the id (hub#416): each record goes by the name
// Sales' screens give it, read as the person, never by its id, and the order type by Kitchen's word. Cancelled: nothing
// is sent nor deleted. What this file creates is deleted after it.
// flow: SALE-F20 SALE-F35 BASE-F97

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { AN_ID } from './assistant-card-helpers';
import { askForACard, cancelAtComputerSize, cancelInSpanish, card, openPanel, sentCard, type SentCard } from './assistant-panel';
import { type Provider } from './assistant-provider';
import { emptyMonth } from './assistant-real';
import { A, api, capture, login, psql, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { seededProvider } from './provider-helpers';
import { cleanSales, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-SALE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
const RUN = stamp();
const VIEWPORTS = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1440', width: 1440, height: 900 },
];

let provider: Provider;
let product: Product;

test.beforeAll(async ({ browser }) => {
  provider = await seededProvider();
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
    emptyMonth();
  }
});

test.beforeEach(() => {
  emptyMonth();
});

const saidBy = (sent: SentCard) => Object.fromEntries(sent.fields.map((field) => [field.name, [field.label, field.value]]));

/** The assistant asks for `tool` with `data`: what the card says, as sent and with its id nowhere. */
async function asked(page: Page, tool: string, data: Record<string, unknown>): Promise<Record<string, unknown[]>> {
  const sent = sentCard(page);
  await askForACard(page, `E2E-ASK ${tool} ${JSON.stringify(data)}`, { timeout: 30_000 });
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
    await cancelAtComputerSize(page);

    expect(await asked(page, 'sale__order__remove_line', { order_id: check.id, line_id: check.lines[0].id })).toMatchObject({
      order_id: ['Cuenta abierta', label],
      line_id: ['Línea', product.name],
    });
    await expect(card(page)).toContainText(product.name);
    await untilStill(page);
    await capture(page, `${KEY}-remove-line-1440`);
    await cancelInSpanish(page);

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
    // A normal write is one line (`cardLine`, BASE-F97): what it touches goes by its value, the title in what the server sent.
    await expect(card(page)).toContainText(name);
    await untilStill(page);
    await capture(page, `${KEY}-section-1440`);
    await cancelInSpanish(page);

    // Cancelled: the section is still there.
    expect(psql(`select count(*) from sale_department where id = '${section.data.id}' and not is_deleted`)).toBe('1');
  } finally {
    await context.close();
  }
});

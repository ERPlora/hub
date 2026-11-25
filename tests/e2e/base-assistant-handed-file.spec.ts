// The CSV an export gives in the assistant's chat: asked for the menu or the customers as a CSV, the owner gets
// «Descargar <file>» under the answer, the same file the screen's export button saves, and the model never had it to
// paste (it hears the file's name only). End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El
// asistente»). What this file creates is named «E2E …» and goes away; the apps it turns on are turned off again.
// flow: INVENTORY-F11 CUSTOMER-F09 BASE-F112
import { readFileSync } from 'node:fs';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { cardSpec } from './assistant-card-helpers';
import { answers, ask, openPanelAtTheDesk, ownerIn, shots } from './assistant-panel';
import { A, api, psql } from './helpers';
import { cleanInventory, createProduct, stamp } from './inventory-helpers';

const TAG = 'E2E Handed';

cardSpec(['tax', 'inventory', 'customer'], () => {
  cleanInventory();
  psql(`delete from customer_activity where customer_id in (select id from customer_customer where name like '${TAG}%'); delete from customer_customer where name like '${TAG}%'`);
});

const fileUnder = (page: Page) => answers(page).last().locator('[data-testid="assistant-file"]');

/** What the browser saves when the person taps the file under the last answer: its name and its text. */
async function downloaded(page: Page): Promise<{ name: string; text: string }> {
  const download = page.waitForEvent('download');
  await fileUnder(page).click();
  const saved = await download;
  return { name: saved.suggestedFilename(), text: readFileSync(await saved.path(), 'utf8') };
}

/** The conversation the panel sends with its next question: what the model may read of the earlier rounds. */
async function nextQuestionSends(page: Page): Promise<string> {
  const sent = page.waitForRequest((request) => request.url().endsWith('/api/assistant/turn') && request.method() === 'POST');
  await ask(page, 'hola');
  return (await sent).postData() ?? '';
}

async function aMenuAndACustomer(context: BrowserContext): Promise<{ dish: string; email: string }> {
  const tag = stamp();
  const dish = `E2E Croquetas ${tag}`;
  await createProduct(context, { name: dish, sku: `E2E-CR-${tag}` });
  const email = `handed-${tag.toLowerCase()}@example.com`;
  const created = await api(context, A, 'POST', '/customer/customers', { name: `${TAG} ${tag}`, email });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  return { dish, email };
}

test('BASE-F112 — the menu and the customers asked as a CSV come to download under the answers, as the screens give them', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  const { dish, email } = await aMenuAndACustomer(context);
  await openPanelAtTheDesk(page);

  await ask(page, 'E2E-ASK inventory__product__export {}');
  await expect(fileUnder(page)).toHaveText('Descargar inventario-productos.csv');
  const menu = await downloaded(page);
  const products = await api<{ content: string }>(context, A, 'GET', '/inventory/products/export');
  expect(menu).toEqual({ name: 'inventario-productos.csv', text: products.data.content });
  expect(menu.text).toContain(dish);
  // The pointer off the button it just tapped: the captures show it at rest, not hovered.
  await page.mouse.move(0, 0);
  await shots(page, 'BASE-G-handed-file', () => expect(fileUnder(page)).toBeVisible());

  await page.setViewportSize({ width: 1440, height: 900 });
  await ask(page, 'E2E-ASK customer__customer__export {}');
  await expect(fileUnder(page)).toHaveText('Descargar customers.csv');
  const customers = await downloaded(page);
  const button = await api<{ csv: string }>(context, A, 'GET', '/customer/customers/export');
  // The Customers button saves its CSV with the mark Excel needs to read it as UTF-8.
  expect(customers).toEqual({ name: 'customers.csv', text: `﻿${button.data.csv}` });
  expect(customers.text).toContain(email);

  const sends = await nextQuestionSends(page);
  expect(sends).toContain('inventario-productos.csv');
  expect(sends).not.toContain(dish);
  expect(sends).not.toContain(email);
  await context.close();
});

test('BASE-F112 — after the page reloads, a file the assistant gave says it is gone and how to get it again', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  await aMenuAndACustomer(context);
  await openPanelAtTheDesk(page);
  await ask(page, 'E2E-ASK inventory__product__export {}');
  await expect(fileUnder(page)).toBeVisible();

  await page.reload();
  await openPanelAtTheDesk(page);
  const gone = answers(page).last().locator('[data-testid="assistant-file-gone"]');
  await expect(gone).toHaveText('El fichero «inventario-productos.csv» ya no está aquí: pídelo otra vez para descargarlo.');
  await expect(fileUnder(page)).toHaveCount(0);
  await shots(page, 'BASE-G-handed-file-gone', () => expect(gone).toBeVisible());
  await context.close();
});

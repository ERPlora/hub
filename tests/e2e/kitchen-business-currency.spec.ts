// flow: KITCHEN-F21 (FIX-HUB-KITCHEN-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/kitchen/WORKBOOK.md «Comandas»)
// Kitchen → Tickets paints each ticket's Total in the business's currency: its country's, as erplora.com registered
// it (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: a
// ticket of the run (made by hand through Kitchen's API with a dish of the catalogue at 24,50) reads its Total in
// złoty and no «€», in 390, 834 and 1440 (captures `FIX-HUB-KITCHEN-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`).
// Back in Spain it reads in euros (`…-es-1440`). What the run creates is deleted after it and `a`'s registration put
// back, also when a test fails.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { createProduct } from './inventory-helpers';
import { stamp } from './sale-helpers';
import { post, settled } from './service-helpers';

const KEY = 'FIX-HUB-KITCHEN-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const RUN = stamp();
const LABEL = `e2e kcur ${RUN}`;
const SKU = `E2E-KCUR-${RUN}`;
/** 24,50 as a till in Poland writes it: «24,50 zł», «zł 24.50». */
const ZLOTY = /zł\s?24[.,]50|24[.,]50\s?zł/;
const EUROS = /€\s?24[.,]50|24[.,]50\s?€/;

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let ticket = { id: '', number: '' };

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

function cleanUp(): void {
  const tickets = `select id from kitchen_ticket where label like 'e2e kcur %'`;
  psql(
    [
      `delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (${tickets}))`,
      `delete from kitchen_logentry where ticket_id in (${tickets})`,
      `delete from kitchen_ticketitem where ticket_id in (${tickets})`,
      `delete from kitchen_ticket where id in (${tickets})`,
    ].join('; '),
  );
  const products = `select id from inventory_product where sku like 'E2E-KCUR-%'`;
  psql(`delete from inventory_stockmovement where product_id in (${products})`);
  psql(`delete from inventory_productcategory where product_id in (${products})`);
  psql(`delete from inventory_product where sku like 'E2E-KCUR-%'`);
}

/** The run's ticket in Kitchen → Tickets, looked up by its destination. */
async function ticketRow(page: Page): Promise<Locator> {
  await page.goto(`${A}/kitchen/tickets`);
  await shown(page).locator('[data-testid=kitchen-tickets-search] input').fill(LABEL);
  const row = shown(page).locator('[data-testid=kitchen-tickets-row]').filter({ hasText: ticket.number }).first();
  await expect(row).toBeVisible();
  return row;
}

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  const context = await browser.newContext({ baseURL: A, locale: 'en-US' });
  await login(await context.newPage(), A, '/kitchen/tickets');
  const dish = await createProduct(context, { name: `E2E KCUR ${RUN} Gambas`, sku: SKU, price: 2450, tax_category_key: 'restaurant.food' });
  ticket = await post<{ id: string; number: string }>(context, '/kitchen/tickets', { label: LABEL, items: [{ product_id: dish.id, quantity: '1' }] });
  await context.close();
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
});

test(`${KEY}: KITCHEN-F21 a business in Poland reads the Total of Kitchen → Tickets in złoty in 390, 834 and 1440`, async ({ page, context }) => {
  await registerBusinessIn(original, 'PL');
  await login(page, A, '/kitchen/tickets');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    const row = await ticketRow(page);
    await expect(row, size.name).toContainText(ZLOTY);
    await expect(row, size.name).not.toContainText('€');
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
  }
});

test(`${KEY}: KITCHEN-F21 back in Spain the Total of Kitchen → Tickets is in euros`, async ({ page }) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/kitchen/tickets');
  const row = await ticketRow(page);
  await expect(row).toContainText(EUROS);
  await expect(row).not.toContainText('zł');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
});

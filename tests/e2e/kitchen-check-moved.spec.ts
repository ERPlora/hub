// KITCHEN-F05 and TABLE-F15 on the screen, against the real API: a round sent from table 4 is on Kitchen → Display as
// «Table 4»; the check is moved to table 9 and, without reloading, the same card says «Table 9», captured at the three
// sizes. What a run creates (its zone, its tables, their check, its product and its kitchen ticket) is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { capture } from './kitchen-helpers';
import { cleanRoom, cleanSales, stamp } from './sale-helpers';
import { ownerPage, post } from './service-helpers';

const RUN = stamp();
const ZONE = `E2E KMV ${RUN}`;

interface Seated {
  id: string;
  order_id: string;
}

interface Ticket {
  id: string;
  label: string;
}

let seated: Seated;
let ticket: Ticket;
let nine: string;

function cleanUp(): void {
  cleanSales();
  cleanRoom('E2E KMV');
  cleanInventory();
}

async function table(context: BrowserContext, zoneId: string, number: string): Promise<string> {
  return (await post<{ id: string }>(context, '/table/tables', { zone_id: zoneId, number, capacity: 4 }, 201)).id;
}

const label = (page: Page): Locator => shown(page).locator(`[data-testid=kitchen-card-${ticket.id}-label]`);

test.use({ locale: 'en-US' });

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/kitchen/display');
  const burger = await createProduct(context, { sku: `E2E-KMV-${RUN}`, name: 'Burger', tax_category_key: 'restaurant.food' });
  const zone = await post<{ id: string }>(context, '/table/zones', { name: ZONE }, 201);
  const four = await table(context, zone.id, '4');
  nine = await table(context, zone.id, '9');
  seated = await post<Seated>(context, '/table/sessions/open', { table_id: four, guests_count: 2 }, 201);
  await post(context, '/sale/orders/add_line', { order_id: seated.order_id, product_id: burger.id, quantity: '1' }, 200);
  ticket = await post<Ticket>(context, '/kitchen/tickets/send', { order_id: seated.order_id }, 201);
  await context.close();
});

test.afterAll(() => {
  cleanUp();
});

test('KITCHEN-F05: a round already sent says the new table once its check is moved, without reloading', async ({ browser }) => {
  expect(ticket.label).toBe('Table 4');
  const { context, page } = await ownerPage(browser, '/kitchen/display');
  try {
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    await page.reload();
    await expect(label(page)).toHaveText('Table 4');

    await post(context, '/table/sessions/transfer', { id: seated.id, to_table_id: nine }, 200);

    await expect(label(page)).toHaveText('Table 9');
    await capture(page, 'F05-moved-check', async () => {
      await label(page).scrollIntoViewIfNeeded();
      await expect(label(page)).toBeInViewport();
    });
  } finally {
    await context.close();
  }
});

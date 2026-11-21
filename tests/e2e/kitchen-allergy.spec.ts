// KITCHEN-F32 on the screen, against the real API: a round whose dish contains the customer's allergy, one whose dish
// does not and one without an allergy, on the display and in the ticket's detail, captured at the three sizes.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { capture } from './kitchen-helpers';
import { cleanSales, stamp } from './sale-helpers';
import { ownerPage, post } from './service-helpers';

const RUN = stamp();
const CHECK = 'e2e allergy';

interface Order {
  id: string;
  lines: { id: string }[];
}

interface Ticket {
  id: string;
  number: string;
  items: { id: string }[];
}

let matching: Ticket;
let notMatching: Ticket;
let plain: Ticket;

function cleanUp(): void {
  cleanSales();
  cleanInventory();
}

async function round(context: BrowserContext, suffix: string, productId: string, allergy: string[]): Promise<Ticket> {
  const order = await post<Order>(context, '/sale/orders', { label: `${CHECK} ${suffix}` }, 201);
  const withDish = await post<Order>(context, '/sale/orders/add_line', { order_id: order.id, product_id: productId, quantity: '1' }, 200);
  if (allergy.length) {
    await post(context, '/sale/orders/set_line_allergy', { order_id: order.id, line_id: withDish.lines[0].id, allergy }, 200);
  }
  return post<Ticket>(context, '/kitchen/tickets/send', { order_id: order.id }, 201);
}

const card = (page: Page, ticket: Ticket): Locator => shown(page).locator(`[data-testid=kitchen-card-${ticket.id}]`);
const mark = (page: Page, ticket: Ticket): Locator => card(page, ticket).locator(`[data-testid=kitchen-card-${ticket.id}-allergy]`);
const notice = (page: Page, ticket: Ticket): Locator =>
  shown(page).locator(`[data-testid=kitchen-line-${ticket.items[0].id}-allergy]`);

async function detail(page: Page, ticket: Ticket): Promise<Locator> {
  await shown(page).locator('[data-testid=kitchen-tickets-search] input').fill(ticket.number);
  await shown(page).locator('[data-testid=kitchen-tickets-row]').filter({ hasText: ticket.number }).first().click();
  const dialog = page.locator('ion-modal[data-testid=kitchen-ticket-detail]');
  await expect(dialog).toBeVisible();
  return dialog;
}

/** The allergy block starts below the dish's name, on a line of its own, and not beside it. */
async function expectUnderTheName(dialog: Locator, block: Locator): Promise<void> {
  const name = await dialog.locator('.kitchen-detail__dishes li > strong').first().boundingBox();
  const notice = await block.boundingBox();
  expect(name && notice && notice.y >= name.y + name.height && notice.x <= name.x).toBe(true);
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/kitchen/display');
  const milk = await createProduct(context, { sku: `E2E-KAL-${RUN}-MILK`, name: 'Flan', allergens: ['milk'] });
  const fish = await createProduct(context, { sku: `E2E-KAL-${RUN}-FISH`, name: 'Hake', allergens: ['fish'] });
  const water = await createProduct(context, { sku: `E2E-KAL-${RUN}-PLAIN`, name: 'Water' });
  matching = await round(context, 'matching', milk.id, ['gluten', 'milk']);
  notMatching = await round(context, 'not matching', fish.id, ['peanut']);
  plain = await round(context, 'plain', water.id, []);
  await context.close();
});

test.afterAll(() => {
  cleanUp();
});

test('KITCHEN-F32: the board marks the allergy on the card and on the dish, and what of it the dish contains', async ({
  browser,
}) => {
  const { context, page } = await ownerPage(browser, '/kitchen/display');
  try {
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    await page.reload();
    await expect(card(page, matching)).toBeVisible();
    await expect(card(page, notMatching)).toBeVisible();
    await expect(card(page, plain)).toBeVisible();
    await expect(mark(page, matching)).toHaveText('Allergy');
    await expect(mark(page, notMatching)).toHaveText('Allergy');
    await expect(mark(page, plain)).toHaveCount(0);
    await expect(notice(page, matching)).toContainText('Allergy: Gluten, Milk');
    await expect(notice(page, matching).locator('[data-testid$=-contains]')).toHaveText('The dish contains Milk');
    await expect(notice(page, notMatching)).toContainText('Allergy: Peanut');
    await expect(notice(page, notMatching).locator('[data-testid$=-contains]')).toHaveCount(0);
    await expect(notice(page, plain)).toHaveCount(0);
    await capture(page, 'F32-board', async () => {
      await notice(page, matching).scrollIntoViewIfNeeded();
      await expect(notice(page, matching)).toBeInViewport();
    });
  } finally {
    await context.close();
  }
});

test('KITCHEN-F32: the ticket detail shows the allergy on its dish the same way', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/tickets');
  try {
    for (const [ticket, allergy, contains, name] of [
      [matching, 'Allergy: Gluten, Milk', 'The dish contains Milk', 'matching'],
      [notMatching, 'Allergy: Peanut', '', 'not-matching'],
      [plain, '', '', 'plain'],
    ] as const) {
      const dialog = await detail(page, ticket);
      const block = dialog.locator(`[data-testid=kitchen-ticket-detail-dish-${ticket.items[0].id}-allergy]`);
      const match = block.locator('[data-testid$=-contains]');
      if (allergy) {
        await expect(block).toContainText(allergy);
        await expectUnderTheName(dialog, block);
      } else await expect(block).toHaveCount(0);
      if (contains) await expect(match).toHaveText(contains);
      else await expect(match).toHaveCount(0);
      await capture(page, `F32-detail-${name}`, async () => {
        await dialog.locator('.kitchen-detail__dishes li').first().scrollIntoViewIfNeeded();
        if (allergy) await expect(block).toBeInViewport();
      });
      await dialog.locator('[data-testid=kitchen-ticket-detail-done]').click();
      await expect(dialog).toBeHidden();
    }
  } finally {
    await context.close();
  }
});

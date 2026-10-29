// flow: customer-business-currency (FIX-HUB-CUSTOMER-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/customer/WORKBOOK.md
// «Clientes», «Ficha de cliente», CUSTOMER-F02, F23 and F31)
// Customers paints and reads money in the business's currency: its country's, as erplora.com registered it
// (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: the list's
// «Spent» and «Revenue» read in złoty and no «€», and «Spent» from «45,50 zł» keeps the card while from «45,51» drops
// it, in 390, 834 and 1440 (captures `FIX-HUB-CUSTOMER-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`); the card's «Spent»
// is in złoty, and among its «Purchases» the one paid in złoty reads in złoty while the one paid in euros before the
// move keeps its euros (a record is never rewritten; `…-card-<width>`). Back in Spain, the same card reads in euros
// (`…-es-1440`). What the run creates is deleted after it and `a`'s registration put back, also when a test fails.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { cleanUp, createCard, customersReady, e2eName, rowNamed, searchList, spanishMobile, type Card } from './customer-helpers';
import { A, horizontalOverflow, hostPage, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { settled } from './service-helpers';

const KEY = 'FIX-HUB-CUSTOMER-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const STAMP = `CCUR${Date.now().toString(36)}`;
/** 45,50 as a till in Poland writes it: «45,50 zł», «zł 45.50». */
const ZLOTY = /zł\s?45[.,]50|45[.,]50\s?zł/;
const PAID_IN_ZLOTY = /zł\s?25[.,]50|25[.,]50\s?zł/;
const PAID_IN_EUROS = /€\s?20[.,]00|20[.,]00\s?€/;
const EUROS = /€\s?45[.,]50|45[.,]50\s?€/;

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let card: Card;

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

const panel = (page: Page): Locator => shown(page).locator('[data-testid=customer-list-filters-panel]');
const toggle = (page: Page): Locator => shown(page).locator('[data-testid=customer-list-filters-toggle]');
const spentFrom = (page: Page): Locator => panel(page).locator('[data-testid=customer-list-filter-spent_from] input');

/** «Spent» from `amount`, typed in the funnel and applied. */
async function spentAtLeast(page: Page, amount: string): Promise<void> {
  await toggle(page).click();
  await expect(panel(page)).toBeVisible();
  await spentFrom(page).fill(amount);
  await page.waitForTimeout(400);
  await panel(page).locator('[data-testid=customer-list-filters-apply]').click();
  await expect(panel(page)).toBeHidden();
}

async function openList(page: Page): Promise<void> {
  await page.goto('/customer/customers');
  await customersReady(page);
  await searchList(page, 'customer-list', STAMP);
  await expect(rowNamed(page, 'customer-list', card.name)).toBeVisible();
}

async function openCard(page: Page): Promise<Locator> {
  await page.goto(`/customer/customers/${card.id}`);
  const facts = shown(page).locator('[data-testid=customer-facts]');
  await expect(facts).toBeVisible();
  return facts;
}

const noHorizontalScroll = (page: Page, size: string) =>
  expect
    .poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${size}` })
    .toBeLessThanOrEqual(0);

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  const owner = await hostPage(browser, A, { next: '/customer/customers' });
  card = await createCard(owner.context, { name: e2eName(`${STAMP} Ana`), phone: spanishMobile() });
  await owner.context.close();
  // Sales reach a card through the sale app's notices (the relay, phase 2): its figures and purchases are set up here,
  // one paid in złoty and one paid in euros before the business moved.
  psql(`update customer_customer set total_purchases = 2, total_spent = 4550, last_purchase_at = now() where id = '${card.id}'`);
  psql(
    `insert into customer_purchase (id, customer_id, sale_id, refund_id, amount, currency, status, recorded_at, void_reason) values ` +
      `(gen_random_uuid(), '${card.id}', gen_random_uuid(), null, 2550, 'PLN', 'confirmed', now(), ''), ` +
      `(gen_random_uuid(), '${card.id}', gen_random_uuid(), null, 2000, 'EUR', 'confirmed', now() - interval '1 day', '')`,
  );
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
});

test(`${KEY}: customer-business-currency a business in Poland reads and types «Spent» in złoty in 390, 834 and 1440`, async ({
  page,
  context,
}) => {
  await registerBusinessIn(original, 'PL');
  await login(page, A, '/customer/customers');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openList(page);
    const row = rowNamed(page, 'customer-list', card.name);
    await expect(row.locator('[data-testid=customer-list-spent]'), size.name).toHaveText(ZLOTY);
    await expect(row, size.name).not.toContainText('€');
    await expect(shown(page).locator('[data-testid=customer-stats-revenue]'), size.name).toContainText('zł');
    await expect(shown(page).locator('[data-testid=customer-stats-revenue]'), size.name).not.toContainText('€');

    // «Spent» is typed in złoty, with its symbol: from 45,50 zł keeps the card (4550), from 45,51 drops it.
    await spentAtLeast(page, '45,50 zł');
    await expect(shown(page).locator('[data-testid=customer-list-filters-count]')).toHaveText('1');
    await expect(rowNamed(page, 'customer-list', card.name)).toBeVisible();
    await settled(page);
    await noHorizontalScroll(page, size.name);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
    await spentAtLeast(page, '45,51');
    await expect(rowNamed(page, 'customer-list', card.name)).toHaveCount(0);

    const facts = await openCard(page);
    await expect(facts, size.name).toContainText(ZLOTY);
    await expect(facts, size.name).not.toContainText('€');
    const purchases = shown(page).locator('[data-testid=customer-purchase]');
    await expect(purchases).toHaveCount(2);
    await expect(purchases.nth(0).locator('.customer-purchases__amount'), size.name).toHaveText(PAID_IN_ZLOTY);
    await expect(purchases.nth(1).locator('.customer-purchases__amount'), size.name).toHaveText(PAID_IN_EUROS);
    await shown(page).locator('[data-testid=customer-purchases]').scrollIntoViewIfNeeded();
    await settled(page);
    await noHorizontalScroll(page, size.name);
    await page.screenshot({ path: shot(`${KEY}-card-${size.name}`) });
  }
});

test(`${KEY}: customer-business-currency back in Spain «Spent» is in euros`, async ({ page }) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/customer/customers');
  await openList(page);
  const row = rowNamed(page, 'customer-list', card.name);
  await expect(row.locator('[data-testid=customer-list-spent]')).toHaveText(EUROS);
  await expect(row).not.toContainText('zł');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
  const facts = await openCard(page);
  await expect(facts).toContainText(EUROS);
  // The purchase paid in złoty keeps its złoty: a record is never rewritten.
  await expect(shown(page).locator('[data-testid=customer-purchase]').nth(0).locator('.customer-purchases__amount')).toHaveText(PAID_IN_ZLOTY);
});

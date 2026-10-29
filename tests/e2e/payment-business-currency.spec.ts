// flow: PAYMENT-F02 (FIX-HUB-PAYMENT-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/payment/WORKBOOK.md «Pagos», PAYMENT-F02 and
// F06; the old payments#35 and #38)
// Payments records, shows and filters in the business's currency: its country's, as erplora.com registered it
// (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: «New
// payment» says «Amount (PLN)», «13,50 €» is not an amount there, «12,50 zł» is recorded as 1250 grosze in PLN and the
// list paints it in złoty beside an older payment that keeps its euros (a record is never rewritten); the amount filter
// (a number field) reads in złoty: from 12.50 keeps it and from 12.51 drops it; in 390, 834 and 1440 (captures
// `FIX-HUB-PAYMENT-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`). Back in Spain, «New payment» says «Amount (EUR)». What
// the run creates is deleted after it and `a`'s registration put back, also when a test fails.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown, untilStill } from './helpers';

const KEY = 'FIX-HUB-PAYMENT-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const TAG = 'E2E PayCur';
const TABLE = 'payment-payments';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const STAMP = Date.now().toString(36);
/** 12,50 as a till in Poland writes it: «12,50 zł», «zł 12.50». */
const ZLOTY = /zł\s?12[.,]50|12[.,]50\s?zł/;
const EUROS = /€\s?20[.,]00|20[.,]00\s?€/;

interface Payment {
  id: string;
  reference: string;
  amount: number;
  currency: string;
}

/** `a`'s registration as the run found it (put back after). */
let original: Registration;

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

/** Deletes what the spec created; the counter of a day goes too when no payment of that day is left. */
function cleanUp(): void {
  const methods = `select id from payment_paymentmethod where name like '${TAG}%'`;
  psql(
    [
      `delete from payment_payment where method_id in (${methods}) or beneficiary_name like '${TAG}%'`,
      `delete from payment_paymentmethod where name like '${TAG}%'`,
      `delete from payment_paymentcounter c where not exists (select 1 from payment_payment p where p.reference like 'PAY-' || to_char(c.day, 'YYYYMMDD') || '-%')`,
    ].join('; '),
  );
}

async function signedIn(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/payment/payments');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

async function post<T>(context: BrowserContext, path: string, body: unknown): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  return res.data;
}

const rowOf = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=${TABLE}-row][data-id="${id}"]`).first();

async function search(page: Page, text: string): Promise<void> {
  await shown(page).locator(`[data-testid=${TABLE}-search] input`).fill(text);
}

/** «Amount» from `amount`, typed behind the funnel and applied («Clear» first). */
async function amountFrom(page: Page, amount: string): Promise<void> {
  await shown(page).locator(`[data-testid=${TABLE}-filters-toggle]`).click();
  const panel = shown(page).locator(`[data-testid=${TABLE}-filters-panel]`);
  await expect(panel).toBeVisible();
  await untilStill(page);
  const clear = panel.locator(`[data-testid=${TABLE}-filters-clear]`);
  const off = () => clear.evaluate((button: HTMLElement & { disabled?: boolean }) => !!button.disabled);
  if (!(await off())) await clear.click();
  await expect.poll(off, 'nothing left to clear').toBe(true);
  await panel.locator(`[data-testid=${TABLE}-filter-amount_from] input`).fill(amount);
  await panel.locator(`[data-testid=${TABLE}-filters-apply]`).click();
  await expect(panel).toBeHidden();
}

/** Picks `text` in the ion-select `testid` (a popover). */
async function choose(page: Page, testid: string, text: string): Promise<void> {
  await page.locator(`[data-testid=${testid}]`).click();
  const option = page.locator('ion-popover').getByText(text, { exact: true });
  await option.click();
  await expect(option).toBeHidden();
}

const noHorizontalScroll = (page: Page, size: string) =>
  expect
    .poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${size}` })
    .toBeLessThanOrEqual(0);

test.beforeAll(() => {
  original = registrationOf('a');
  cleanUp();
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
});

test(`${KEY}: PAYMENT-F02 a business in Poland records, shows and filters its payments in złoty in 390, 834 and 1440`, async ({ browser }) => {
  await registerBusinessIn(original, 'PL');
  const { context, page } = await signedIn(browser);
  try {
    const bank = await post<{ id: string; name: string }>(context, '/payment/methods', { name: `${TAG} Bank ${STAMP}` });
    // A payment recorded in euros before the business moved keeps its euros.
    const older = await post<Payment>(context, '/payment/payments', {
      method_id: bank.id,
      payment_date: '2026-10-01',
      amount: 2000,
      currency: 'EUR',
      beneficiary_name: `${TAG} Older ${STAMP}`,
    });

    await shown(page).locator(`[data-testid=${TABLE}-add]`).click();
    const form = page.locator('ion-modal[data-testid=payment-form]');
    await expect(form).toBeVisible();
    await expect(page.locator('[data-testid=payment-form-amount]')).toHaveJSProperty('label', 'Amount (PLN)');
    await page.screenshot({ path: shot(`${KEY}-form-1440`) });
    await choose(page, 'payment-form-method', bank.name);
    const supplier = `${TAG} Dostawca ${STAMP}`;
    await page.locator('[data-testid=payment-form-beneficiary] input').fill(supplier);
    // A euro is not an amount in Poland: said under the field, nothing recorded.
    await page.locator('[data-testid=payment-form-amount] input').fill('13,50 €');
    await page.locator('[data-testid=payment-form-submit]').click();
    await expect(page.locator('[data-testid=payment-form-amount]')).toContainText('This is not an amount. Type a figure, for example 12.50.');
    expect(psql(`select count(*) from payment_payment where beneficiary_name = '${supplier}'`)).toBe('0');
    await page.locator('[data-testid=payment-form-amount] input').fill('12,50 zł');
    await page.locator('[data-testid=payment-form-submit]').click();
    await expect(form).toBeHidden();
    await expect.poll(() => psql(`select amount || ' ' || currency from payment_payment where beneficiary_name = '${supplier}'`)).toBe('1250 PLN');
    const id = psql(`select id from payment_payment where beneficiary_name = '${supplier}'`);

    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto('/payment/payments');
      await search(page, STAMP);
      const recorded = rowOf(page, id);
      await expect(recorded, size.name).toContainText(ZLOTY);
      await expect(recorded, size.name).not.toContainText('€');
      await expect(rowOf(page, older.id), size.name).toContainText(EUROS);

      // The amount filter reads in złoty, with its two decimals: from 12.50 keeps the payment (1250 grosze), from 12.51
      // drops it (the funnel's field takes a number: no symbol is typed there).
      await amountFrom(page, '12.51');
      await expect(shown(page).locator(`[data-testid=${TABLE}-row][data-id="${id}"]`), size.name).toHaveCount(0);
      await amountFrom(page, '12.50');
      await expect(rowOf(page, id), size.name).toBeVisible();
      await expect(shown(page).locator(`[data-testid=${TABLE}-row][data-id="${older.id}"]`), size.name).toBeVisible();
      await untilStill(page);
      await noHorizontalScroll(page, size.name);
      await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
    }
  } finally {
    await context.close();
  }
});

test(`${KEY}: PAYMENT-F02 back in Spain «New payment» says «Amount (EUR)» and records in euros`, async ({ browser }) => {
  await registerBusinessIn(original, 'ES');
  const { context, page } = await signedIn(browser);
  try {
    const bank = await post<{ id: string; name: string }>(context, '/payment/methods', { name: `${TAG} Banco ${STAMP}` });
    const created = await post<Payment>(context, '/payment/payments', {
      method_id: bank.id,
      payment_date: '2026-10-14',
      amount: 2000,
      beneficiary_name: `${TAG} Proveedor ${STAMP}`,
    });
    expect(created.currency).toBe('EUR');
    await shown(page).locator(`[data-testid=${TABLE}-add]`).click();
    await expect(page.locator('ion-modal[data-testid=payment-form]')).toBeVisible();
    await expect(page.locator('[data-testid=payment-form-amount]')).toHaveJSProperty('label', 'Amount (EUR)');
  } finally {
    await context.close();
  }
});

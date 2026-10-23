// flow: PAYMENT-F06 (lista de Pagos: filtros tras el embudo) — FIX-HUB-PAYMENT-LIST-FILTERS-BEHIND-FUNNEL (seen by the
// reviewer of FIX-UI-DATATABLE-RANGE-FILTER-LABELS): the old Payments › Payments kept its column filters behind the
// toolbar's funnel (docs/reference/old-hub/payment-list-{390,834,1440}.png: search, «Columns», page size, views, funnel
// and «Add», no row of filters open). The new list painted that row open under the toolbar at 834 and 1440. As
// Invoices, Sales or Customers, on arrival there is only the funnel; it opens the panel inside the table (1440, 834) or
// the sheet over the list (390) with the same filters (Reference, Date from / to, Beneficiary, Amount from / to,
// Status), and «Apply» still filters the list by status, by date and by amount in euros.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown, untilStill } from './helpers';

const KEY = 'FIX-HUB-PAYMENT-LIST-FILTERS-BEHIND-FUNNEL';
const TABLE = 'payment-payments';
const TAG = 'E2E Funnel';
/** Every filter of the old list, by its control: a range gives its two ends. */
const FILTERS = ['reference', 'payment_date_from', 'payment_date_to', 'beneficiary_name', 'amount_from', 'amount_to', 'status'];
const SIZES = [
  { label: '1440', width: 1440, height: 900, sheet: false },
  { label: '834', width: 834, height: 1112, sheet: false },
  { label: '390', width: 390, height: 844, sheet: true },
] as const;

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

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

interface Payment {
  id: string;
  reference: string;
}

async function post<T>(context: BrowserContext, path: string, body: Record<string, unknown>, status: number): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, JSON.stringify(res.data)).toBe(status);
  return res.data;
}

/** Two payments only this run finds by its stamp: an approved one in August for 40 € and a draft in September for 125.50 €. */
async function twoPayments(context: BrowserContext, stamp: string): Promise<{ august: Payment; september: Payment }> {
  const method = await post<{ id: string }>(context, '/payment/methods', { name: `${TAG} Bank ${stamp}`, bank_account_ref: '' }, 201);
  const make = (payment_date: string, amount: number, who: string) =>
    post<Payment>(context, '/payment/payments', { method_id: method.id, payment_date, amount, beneficiary_name: `${TAG} ${who} ${stamp}` }, 201);
  const august = await make('2026-08-21', 4000, 'August');
  const september = await make('2026-09-15', 12550, 'September');
  await post(context, '/payment/payments/approve', { id: august.id }, 200);
  return { august, september };
}

const rowOf = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=${TABLE}-row][data-id="${id}"]`).first();

/** Exactly these payments are listed (rows, or cards on a phone). */
async function listed(page: Page, seen: Payment[], hidden: Payment[]): Promise<void> {
  for (const payment of seen) await expect(rowOf(page, payment.id)).toBeVisible();
  for (const payment of hidden) await expect(shown(page).locator(`[data-testid=${TABLE}-row][data-id="${payment.id}"]`)).toHaveCount(0);
}

/** Opens the funnel: its panel, standing still once it has slid in. */
async function openFunnel(page: Page): Promise<Locator> {
  await shown(page).locator(`[data-testid=${TABLE}-filters-toggle]`).click();
  const panel = shown(page).locator(`[data-testid=${TABLE}-filters-panel]`);
  await expect(panel).toBeVisible();
  await untilStill(page);
  return panel;
}

/** «Clear» lifts every filter (it is off while none is set); then `set` fills the draft and «Apply» applies it and closes the panel. */
async function filterWith(page: Page, set: (panel: Locator) => Promise<void>): Promise<void> {
  const panel = await openFunnel(page);
  // An ion-button keeps `disabled` on its host, where Playwright's `isEnabled` does not look.
  const clear = panel.locator(`[data-testid=${TABLE}-filters-clear]`);
  const off = () => clear.evaluate((button: HTMLElement & { disabled?: boolean }) => !!button.disabled);
  if (!(await off())) await clear.click();
  await expect.poll(off, 'nothing left to clear').toBe(true);
  await set(panel);
  await panel.locator(`[data-testid=${TABLE}-filters-apply]`).click();
  await expect(panel).toBeHidden();
}

/** Picks a status in the panel's select (an ion-select popover). */
async function pickStatus(page: Page, panel: Locator, label: string): Promise<void> {
  const popover = page.locator('ion-popover.select-popover');
  await panel.locator(`[data-testid=${TABLE}-filter-status]`).click();
  await popover.locator('ion-radio').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) }).click();
  await expect(popover).toHaveCount(0);
}

async function signedIn(browser: Browser, size: (typeof SIZES)[number]): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: size.width, height: size.height }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/payment/payments');
  return { context, page };
}

for (const size of SIZES) {
  test(`PAYMENT-F06 (lista de Pagos: filtros tras el embudo) at ${size.label}: no filter row on arrival, the funnel opens ${size.sheet ? 'the sheet' : 'the panel'} with the same filters and «Apply» filters by status, date and amount`, async ({
    browser,
  }) => {
    const { context, page } = await signedIn(browser, size);
    try {
      const stamp = `${size.label}-${Date.now().toString(36)}`;
      const { august, september } = await twoPayments(context, stamp);
      const view = shown(page);
      await view.locator(`[data-testid=${TABLE}-empty], [data-testid=${TABLE}-row]`).first().waitFor({ state: 'visible' });
      await view.locator(`[data-testid=${TABLE}-search] input`).fill(stamp);
      await listed(page, [august, september], []);

      // On arrival, as the old list: the funnel in the toolbar, no row of filters, no panel.
      const funnel = view.locator(`[data-testid=${TABLE}-filters-toggle]`);
      await expect(funnel, 'the funnel is in the toolbar').toBeVisible();
      await expect(view.locator(`[data-testid=${TABLE}-filters]`), 'no filter row open').toHaveCount(0);
      await expect(view.locator(`[data-testid=${TABLE}-filters-panel]`)).toHaveCount(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });

      // The funnel opens the same filters: inside the table on a desk, a modal sheet over the list on a phone.
      const panel = await openFunnel(page);
      if (size.sheet) await expect(panel).toHaveAttribute('aria-modal', 'true');
      else await expect(panel).not.toHaveAttribute('aria-modal', 'true');
      for (const name of FILTERS) await expect(panel.locator(`[data-testid=${TABLE}-filter-${name}]`), `${name} behind the funnel`).toHaveCount(1);
      if (size.label === '834') await page.screenshot({ path: shot(`${KEY}-834-open`) });
      await panel.locator(`[data-testid=${TABLE}-filters-close]`).click();
      await expect(panel).toBeHidden();

      // By status: Approved keeps August's only, and the funnel counts one filter.
      await filterWith(page, (scope) => pickStatus(page, scope, 'Approved'));
      await listed(page, [august], [september]);
      await expect(view.locator(`[data-testid=${TABLE}-filters-count]`)).toHaveText('1');

      // By date: from the 1st to the 30th of September keeps September's only.
      await filterWith(page, async (scope) => {
        await scope.locator(`[data-testid=${TABLE}-filter-payment_date_from] input`).fill('2026-09-01');
        await scope.locator(`[data-testid=${TABLE}-filter-payment_date_to] input`).fill('2026-09-30');
      });
      await listed(page, [september], [august]);

      // By amount in euros: from 100 € keeps the 125.50 € one only (never read as cents).
      await filterWith(page, (scope) => scope.locator(`[data-testid=${TABLE}-filter-amount_from] input`).fill('100'));
      await listed(page, [september], [august]);
    } finally {
      await context.close();
    }
  });
}

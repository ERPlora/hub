// flow: BASE-G96 BASE-G97 BASE-G98 BASE-G99 (base/WORKBOOK.md) · HUBS-F15 of the SaaS (hubs/WORKBOOK.md)
// Settings (APP-BASE-6; the old hub's settings-*.png) in the three viewports, against the real Hub and the real SaaS of
// this run's stack (the SaaS's `HUB_INTERNAL_URL` points here): a fresh owner signs up on the SaaS's screens and creates
// a business through its API as the panel does, so the SaaS registers it in this Hub with the same id.
//   - BASE-G96: «Settings» from the side menu opens «Business»; its three tabs fit the phone; a tab is in the address
//     (replaced: Back leaves Settings); «Printing» opens the Printing app.
//   - BASE-G97, G98: «Business» shows the country (Spain) and its currency (EUR · Euro), read-only, and where they change;
//     «Fiscal data» opens Invoicing's issuer.
//   - BASE-G99: the owner changes the business's language on erplora.com (HUBS-F15, the panel's own call); the open tab
//     shows it without reloading. «Change on erplora.com» opens the business's settings there, in a new tab.
//   - BASE-G98 on the Home: the amounts of «Sales, last 7 days» are in the business's currency — euros in the business
//     in Spain, złoty in a second one in Poland (`APP-BASE-6-BASE-G98-HOME-<width>`) —, never a fixed euro.
// Each flow leaves its capture `APP-BASE-6-<key>-<width>`.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { api, type Credentials, login, MAIL_DIR, psql, SAAS, shot, shown, untilStill } from './helpers';
import { readMailCode } from './mail';
import { STACK } from './stack';

test.use({ actionTimeout: 30_000 });

const PASSWORD = 'Masa-madre-y-centeno-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
/** What the SaaS's steps wait (its pushes to this Hub happen after its COMMIT). */
const SAAS_STEP = 30_000;

interface Owner {
  context: BrowserContext;
  page: Page;
  credentials: Credentials;
}

interface Business {
  id: string;
  slug: string;
}

/** A fresh account signed up on the SaaS's «Create account», its address proven with the mailed code; signed in. */
async function signUp(browser: Browser): Promise<Owner> {
  const credentials = { email: `e2e-settings-${Date.now()}@example.com`, password: PASSWORD };
  const context = await browser.newContext({ locale: 'en-US', viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${SAAS}/launch?tab=signup`);
  const form = page.getByTestId('login-form');
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  const since = Date.now() - 50;
  await form.getByTestId('login-submit').click();
  await expect(page).toHaveURL(/\/verify-email$/);
  const code = await readMailCode({ dir: MAIL_DIR, to: credentials.email, since, timeout: SAAS_STEP });
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();
  await expect(page).toHaveURL(/\/launch$/);
  return { context, page, credentials };
}

/** A POST to the SaaS's API as `context`'s account, with the SaaS's CSRF token. */
async function saasPost(context: BrowserContext, path: string, data: unknown) {
  const host = new URL(SAAS).hostname;
  const csrf = (await context.cookies(SAAS)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value;
  if (!csrf) throw new Error(`POST ${path}: no csrftoken of the SaaS (sign in first)`);
  return context.request.post(`${SAAS}/api${path}`, { headers: { 'X-CSRFToken': csrf }, data });
}

/** The owner's new business in `country`, once the SaaS registered it in this Hub and heard it is ready. */
async function businessOf(owner: Owner, country = 'ES'): Promise<Business> {
  const created = await saasPost(owner.context, '/hubs/businesses', { name: `Ajustes ${Date.now().toString(36)}`, country });
  expect(created.status(), await created.text()).toBe(201);
  const business = (await created.json()) as Business;
  await expect
    .poll(() => psql(`SELECT status FROM base_hub WHERE id = '${business.id}'`), { timeout: SAAS_STEP, message: 'registered here' })
    .toBe('ready');
  return business;
}

/** The business's language, changed on erplora.com as its panel changes it (HUBS-F15). */
async function changeLanguage(owner: Owner, business: Business, language: 'en' | 'es'): Promise<void> {
  const changed = await saasPost(owner.context, '/hubs/businesses/update', { id: business.id, language });
  expect(changed.status(), await changed.text()).toBe(200);
}

/** The Home's panel the currency is read on (Sales' «Sales, last 7 days»): alone on this browser's board, which the
 *  Home keeps in `dashboard-hub` (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const WEEK = 'sale.last_7_days';

async function onlyTheWeek(context: BrowserContext): Promise<void> {
  await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), ['dashboard-hub', JSON.stringify([WEEK])]);
}

const weekPanel = (page: Page): Locator =>
  shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${WEEK}"]`);

/** The value a row of «Business» shows. */
const rowValue = (page: Page, row: string): Locator =>
  shown(page).locator(`[data-testid="business-${row}"] [data-testid="settings-row-value"]`);

/** `ready` at each size and a capture `APP-BASE-6-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, keys: string[], ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await untilStill(page);
    for (const key of keys) await page.screenshot({ path: shot(`APP-BASE-6-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test('BASE-G96 BASE-G97 BASE-G98 BASE-G99 — Settings › Business and Printing, and a change made on erplora.com', async ({
  browser,
}) => {
  test.setTimeout(240_000);
  const owner = await signUp(browser);
  const business = await businessOf(owner);
  const origin = STACK.hub(business.slug);
  await changeLanguage(owner, business, 'es');
  const page = await owner.context.newPage();
  await login(page, origin, '/', owner.credentials);

  // BASE-G96: «Settings» from the side menu opens its first tab, «Business».
  await page.locator('ion-item.nav-item', { hasText: 'Settings' }).first().click();
  await expect(page).toHaveURL(new RegExp(`^${origin}/settings`));
  await expect(rowValue(page, 'name')).toHaveText(/^Ajustes /);

  // BASE-G97, G98: the country and its currency, as erplora.com registered the business; nothing to type.
  await expect(rowValue(page, 'country')).toHaveText('Spain');
  await expect(rowValue(page, 'currency')).toHaveText('EUR · Euro');
  await expect(rowValue(page, 'timezone')).toHaveText(/^Europe\/Madrid · \d\d:\d\d$/);
  await expect(rowValue(page, 'language')).toHaveText('Spanish');
  await expect(shown(page).locator('ion-input, ion-select, input, select')).toHaveCount(0);
  await expect(shown(page).getByTestId('business-where')).toHaveText(
    'The name, the time zone and the language are changed on erplora.com. The country does not change once the business is ready.',
  );
  await atEverySize(page, ['BASE-G97', 'BASE-G98'], async () => {
    await expect(rowValue(page, 'currency')).toBeVisible();
    // gh:hub#2617 — the three tabs fit the phone: none under the edge, none cut.
    for (const tab of ['business', 'tickets', 'data']) {
      const box = await shown(page).getByTestId(`tab-${tab}`).boundingBox();
      expect(box, tab).not.toBeNull();
      expect(box!.x, tab).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width, tab).toBeLessThanOrEqual(page.viewportSize()!.width);
    }
  });

  // BASE-G99: the language changed on erplora.com shows in the open tab without reloading.
  let reloaded = false;
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) reloaded = true;
  });
  await changeLanguage(owner, business, 'en');
  await expect(rowValue(page, 'language')).toHaveText('English', { timeout: SAAS_STEP });
  expect(reloaded, 'the page was not reloaded').toBe(false);
  await atEverySize(page, ['BASE-G99'], async () => {
    await expect(rowValue(page, 'language')).toHaveText('English');
  });

  // «Change on erplora.com»: the business's settings there, in a new tab.
  const [popup] = await Promise.all([
    owner.context.waitForEvent('page'),
    shown(page).getByTestId('business-change').click(),
  ]);
  await expect(popup).toHaveURL(`${SAAS}/businesses/${business.id}/settings`);
  await popup.close();

  // «Fiscal data»: Invoicing's issuer, where the invoices take it from.
  await shown(page).getByTestId('business-fiscal').click();
  await expect(page).toHaveURL(`${origin}/invoice/issuer`);
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`^${origin}/settings`));

  // BASE-G96: «Printing», in the address and replaced (Back leaves Settings); its row opens the Printing app.
  await shown(page).getByTestId('tab-tickets').click();
  await expect(page).toHaveURL(`${origin}/settings#tickets`);
  const printers = shown(page).getByTestId('tickets-printers');
  await expect(printers.getByTestId('settings-row-title')).toHaveText('Printers and ticket');
  await atEverySize(page, ['BASE-G96'], async () => {
    await expect(printers).toBeVisible();
  });
  await printers.click();
  await expect(page).toHaveURL(`${origin}/printing/printers`);
  await page.goBack();
  await expect(page).toHaveURL(`${origin}/settings#tickets`);
  await page.goBack();
  await expect(page).not.toHaveURL(/\/settings/);

  // An old address still lands: `#tax` (published versions of VeriFactu link it) opens «Business».
  await page.goto(`${origin}/settings#tax`);
  await expect(rowValue(page, 'country')).toHaveText('Spain');

  // BASE-G98 on the Home: the amounts of this business in Spain are in euros.
  await onlyTheWeek(owner.context);
  await page.goto(`${origin}/`);
  await expect(weekPanel(page).locator('[data-testid="widget-chart-amount"]')).toHaveText(/^€[\d,]+\.\d\d$/);
  await owner.context.close();
});

test('BASE-G98 — the Home of a business in Poland writes its amounts in złoty, never in euros', async ({ browser }) => {
  test.setTimeout(240_000);
  const owner = await signUp(browser);
  const business = await businessOf(owner, 'PL');
  const origin = STACK.hub(business.slug);
  await onlyTheWeek(owner.context);
  const page = await owner.context.newPage();
  await login(page, origin, '/', owner.credentials);
  if (process.env.E2E_SAVE_STORAGE_STATE) await owner.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });

  // What Settings › Business says (its country's currency) and the server's seven days, in cents.
  const said = await api<{ country: string; currency: string; currency_decimals: number }>(owner.context, origin, 'GET', '/business');
  expect(said.status).toBe(200);
  expect(said.data).toMatchObject({ country: 'PL', currency: 'PLN', currency_decimals: 2 });
  const week = await api<{ rows: { day: string; total: number }[] }>(owner.context, origin, 'GET', '/sale/sales/last_7_days');
  expect(week.status).toBe(200);
  expect(week.data.rows).toHaveLength(7);
  // Each day's amount as the browser itself writes the złoty in the person's language (as a till in Poland: «zł»).
  const zloty = await page.evaluate(
    (totals) => {
      const format = new Intl.NumberFormat(document.documentElement.lang, {
        style: 'currency',
        currency: 'PLN',
        currencyDisplay: 'narrowSymbol',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      return totals.map((total) => format.format(total / 100));
    },
    week.data.rows.map((row) => row.total),
  );
  expect(zloty.every((amount) => amount.includes('zł'))).toBe(true);

  const panel = weekPanel(page);
  await expect(panel).toHaveAttribute('aria-busy', 'false');
  const amount = panel.locator('[data-testid="widget-chart-amount"]');
  await expect(amount).toHaveText(zloty[6]);
  // Each bar says its day and its amount, in złoty; nothing on the board in euros.
  const labels = await panel.locator('[data-testid="widget-chart-bar"]').evaluateAll((bars) => bars.map((bar) => bar.getAttribute('aria-label') ?? ''));
  expect(labels.map((label) => label.slice(label.lastIndexOf(': ') + 2))).toEqual(zloty);
  await expect(shown(page).getByTestId('widget-board')).not.toContainText('€');
  await atEverySize(page, ['BASE-G98-HOME'], async () => {
    await expect(amount).toHaveText(zloty[6]);
    await panel.evaluate((element) => element.scrollIntoView({ block: 'center' }));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `no sideways scroll at ${page.viewportSize()!.width}`).toBeLessThanOrEqual(0);
  });
  await owner.context.close();
});

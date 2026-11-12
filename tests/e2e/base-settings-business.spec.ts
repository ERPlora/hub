// flow: HUBS-F15 of the SaaS (hubs/WORKBOOK.md)
// Against the real Hub and the real SaaS of this run's stack (the SaaS's `HUB_INTERNAL_URL` points here): a fresh
// owner signs up on the SaaS's screens and creates a business through its API as the panel does, so the SaaS registers
// it in this Hub with the same id.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { api, horizontalOverflow, login, SAAS, shot, shown, turnOn, untilStill } from './helpers';
import { businessOnSaas, type SaasBusiness, type SaasOwner, saasPost, signUpOnSaas } from './saas-owner';
import { STACK } from './stack';

test.use({ actionTimeout: 30_000 });

const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
/** What the SaaS's steps wait (its pushes to this Hub happen after its COMMIT). */
const SAAS_STEP = 30_000;

/** The owner's new business in `country`, created on erplora.com (`businessOnSaas`). */
const businessOf = (owner: SaasOwner, country = 'ES'): Promise<SaasBusiness> =>
  businessOnSaas(owner, { name: `Ajustes ${Date.now().toString(36)}`, country });

/** The business's language, changed on erplora.com as its panel changes it (HUBS-F15). */
async function changeLanguage(owner: SaasOwner, business: SaasBusiness, language: 'en' | 'es'): Promise<void> {
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

/** `ready` at each size and a capture; back at 1440 after. */
async function atEverySize(page: Page, keys: string[], ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await untilStill(page);
    for (const key of keys) await page.screenshot({ path: shot(`APP-BASE-6-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test('Settings › Business and Printing, and a change made on erplora.com', async ({
  browser,
}) => {
  test.setTimeout(240_000);
  const owner = await signUpOnSaas(browser, 'settings');
  const business = await businessOf(owner);
  const origin = STACK.hub(business.slug);
  await changeLanguage(owner, business, 'es');
  const page = await owner.context.newPage();
  await login(page, origin, '/', owner.credentials);
  // A business is born with every app off but Taxes (PLAN-HUB rounds 2026-10-27 and 2026-11-07): the ones these screens
  // open, and the Home's sales;
  // the page reads its session again, whose menu has them now.
  await turnOn(owner.context, origin, 'sale', 'invoice', 'printing');
  await page.reload();

  // «Settings» from the side menu opens its first tab, «General»; «Business» is the next one.
  await page.locator('ion-item.nav-item', { hasText: 'Settings' }).first().click();
  await expect(page).toHaveURL(new RegExp(`^${origin}/settings`));
  await expect(shown(page).getByTestId('tab-general')).toHaveClass(/segment-button-checked/);
  await shown(page).getByTestId('tab-business').click();
  await expect(page).toHaveURL(`${origin}/settings#business`);
  await expect(rowValue(page, 'name')).toHaveText(/^Ajustes /);

  // The country and its currency, as erplora.com registered the business; nothing to type.
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
    // The four tabs fit the phone: none under the edge, none cut.
    for (const tab of ['general', 'business', 'tickets', 'data']) {
      const box = await shown(page).getByTestId(`tab-${tab}`).boundingBox();
      expect(box, tab).not.toBeNull();
      expect(box!.x, tab).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width, tab).toBeLessThanOrEqual(page.viewportSize()!.width);
    }
  });

  // The language changed on erplora.com shows in the open tab without reloading.
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
  await expect(popup).toHaveURL(`${SAAS}/dashboard/businesses/${business.id}/settings`);
  await popup.close();

  // «Fiscal data»: Invoicing's issuer, where the invoices take it from.
  await shown(page).getByTestId('business-fiscal').click();
  await expect(page).toHaveURL(`${origin}/invoice/issuer`);
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`^${origin}/settings`));

  // «Printing», in the address and replaced (Back leaves Settings); its row opens the Printing app.
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

  // On the Home, the amounts of this business in Spain are in euros.
  await onlyTheWeek(owner.context);
  await page.goto(`${origin}/`);
  await expect(weekPanel(page).locator('[data-testid="widget-chart-amount"]')).toHaveText(/^€[\d,]+\.\d\d$/);
  await owner.context.close();
});

test('the Home of a business in Poland writes its amounts in złoty, never in euros', async ({ browser }) => {
  test.setTimeout(240_000);
  const owner = await signUpOnSaas(browser, 'settings');
  const business = await businessOf(owner, 'PL');
  const origin = STACK.hub(business.slug);
  await onlyTheWeek(owner.context);
  const page = await owner.context.newPage();
  await login(page, origin, '/', owner.credentials);
  await turnOn(owner.context, origin, 'sale'); // born without Sales: the Home's week of sales
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
    // Once the shell has laid itself out at the new size: right after the resize the bar's buttons of the wide layout
    // are still there for a moment (hub#997's run caught it 3 times in 12); an overflow that stays still fails.
    await expect
      .poll(() => horizontalOverflow(page), { message: `no sideways scroll at ${page.viewportSize()!.width}` })
      .toBeLessThanOrEqual(0);
  });
  await owner.context.close();
});

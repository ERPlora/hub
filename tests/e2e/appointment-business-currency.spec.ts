// flow: BASE-F50 APPOINTMENT-F01 ONLINE_BOOKING-F01 (hub#577; base, apps/appointment and apps/online_booking WORKBOOK.md)
// Appointments paints its prices in the business's currency: its country's, as erplora.com registered it
// (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: in «New
// appointment» the service offered and the «Total» are in złoty, and so is the service in the preview of the online
// booking page, in 390, 834 and 1440 (captures `APPOINTMENT-BUSINESS-CURRENCY-<width>`, `…-option-<width>` and
// `…-preview-<width>`). Back in Spain they are in euros (`…-es-1440`). What the run creates is deleted after it, and
// `a`'s registration and whether its online page takes bookings are put back, also when a test fails.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, hostPage, login, registerBusinessIn, registrationOf, type Registration, settled, shown } from './helpers';
import { cleanUp, FLOW_VIEWPORTS, named, noHorizontalScroll, post } from './service-helpers';

const KEY = 'APPOINTMENT-BUSINESS-CURRENCY';
/** An amount in `symbol` as a till writes it, before or after the figure («22,50 zł», «zł 22.50»). */
const inCurrency = (symbol: string, figure = '22[.,]50'): RegExp => new RegExp(`${symbol}\\s?${figure}|${figure}\\s?${symbol}`);

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
/** Whether the online page took bookings when the run started (put back after). */
let wasEnabled: boolean | null = null;
/** A bookable service of the run, booked online too: 22,50 in the business's money. */
let service = { id: '', name: '' };

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

async function withOwner<T>(browser: Parameters<typeof hostPage>[0], act: (context: BrowserContext) => Promise<T>): Promise<T> {
  const owner = await hostPage(browser, A, { next: '/appointment/agenda' });
  try {
    return await act(owner.context);
  } finally {
    await owner.context.close();
  }
}

/** «New appointment» with the run's service searched: the option offered for it and the panel. */
async function offered(page: Page): Promise<{ option: Locator; form: Locator }> {
  await page.goto(`${A}/appointment/agenda`);
  const view = shown(page);
  await view.locator('[data-testid=appointment-list-empty], [data-testid=appointment-list-row]').first().waitFor({ state: 'visible' });
  await view.locator('[data-testid=appointment-list-add]').click();
  const form = page.locator('ion-modal[data-testid=appointment-form]');
  await expect(form).toBeVisible();
  await form.locator('[data-testid=appointment-form-service-add] input').fill(service.name);
  return { option: page.locator(`[data-testid=appointment-form-service-add-option-${service.id}]`), form };
}

/** The run's service in the preview of the online booking page. */
async function previewed(page: Page): Promise<Locator> {
  await page.goto(`${A}/online_booking/preview`);
  const row = shown(page).locator(`[data-testid=ob-preview-service-${service.id}]`);
  await expect(row).toBeVisible();
  return row;
}

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  await withOwner(browser, async (context) => {
    const name = named('Corte moneda');
    const created = await post<{ id: string }>(context, '/service/services', {
      name,
      price: 2250,
      duration_minutes: 30,
      allow_online_booking: true,
      tax_category_key: 'service.generic',
    });
    service = { id: created.id, name };
    const settings = await api<{ is_enabled: boolean }>(context, A, 'GET', '/online_booking/settings');
    expect(settings.status).toBe(200);
    wasEnabled = settings.data.is_enabled;
    await post(context, '/online_booking/settings', { is_enabled: true }, 200);
  });
});

test.afterAll(async ({ browser }) => {
  if (original) await registerBusinessIn(original, original.country);
  if (wasEnabled !== null) await withOwner(browser, (context) => post(context, '/online_booking/settings', { is_enabled: wasEnabled }, 200));
  cleanUp();
});

test(`${KEY}: a business in Poland books and previews its services in złoty, never euros, in 390, 834 and 1440`, async ({ page }) => {
  await registerBusinessIn(original, 'PL');
  await login(page, A, '/appointment/agenda');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of FLOW_VIEWPORTS) {
    const where = `at ${size.label}`;
    await page.setViewportSize({ width: size.width, height: size.height });
    const { option, form } = await offered(page);
    await expect(option, `the service offered ${where}`).toContainText(inCurrency('zł'));
    await expect(option, `the service offered ${where}`).not.toContainText('€');
    await capture(page, `${KEY}-option-${size.label}`);
    await option.click();
    const total = form.locator('[data-testid=appointment-form-total]');
    await expect(total, `the Total ${where}`).toContainText(inCurrency('zł'));
    await expect(total, `the Total ${where}`).not.toContainText('€');
    await total.scrollIntoViewIfNeeded();
    await settled(page);
    await noHorizontalScroll(page, `New appointment ${where}`);
    await capture(page, `${KEY}-${size.label}`);
    await form.locator('[data-testid=appointment-form-cancel]').click();
    await expect(form).toBeHidden();

    const row = await previewed(page);
    await expect(row, `the preview ${where}`).toContainText(inCurrency('zł'));
    await expect(row, `the preview ${where}`).not.toContainText('€');
    await settled(page);
    await noHorizontalScroll(page, `the preview ${where}`);
    await capture(page, `${KEY}-preview-${size.label}`);
  }
});

test(`${KEY}: back in Spain the services are booked and previewed in euros`, async ({ page }) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/appointment/agenda');
  const { option, form } = await offered(page);
  await expect(option).toContainText(inCurrency('€'));
  await option.click();
  await expect(form.locator('[data-testid=appointment-form-total]')).toContainText(inCurrency('€'));
  await expect(form.locator('[data-testid=appointment-form-total]')).not.toContainText('zł');
  await capture(page, `${KEY}-es-1440`);
  await form.locator('[data-testid=appointment-form-cancel]').click();
  await expect(await previewed(page)).toContainText(inCurrency('€'));
});

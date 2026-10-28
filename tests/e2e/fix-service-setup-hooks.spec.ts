// flow: SERVICE-F01
// Services' hook of the Home (FIX-SERVICE-SETUP-HOOKS; the old module's own `setup` item «Tu catálogo de servicios»,
// services#26; the old hub's dashboard in docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads it in
// Spanish: «Tu catálogo de servicios» pending and «Importante» in «Termina de configurar tu negocio» while no service
// can be charged, its «Configurar» leading to Services, where the first one is added at a closed price; then «Hecho»,
// back to pending without a reload when that service is archived and «Hecho» again when it is restored. In each of the
// three sizes, the capture `FIX-SERVICE-SETUP-HOOKS-<width>` with the step pending in sight. The services the hub
// already had on offer are archived for the run and back on offer after it; the run's own are «E2E Svc …», deleted by
// `cleanUp()` before and after.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown, untilStill } from './helpers';
import { VIEWPORTS } from './inventory-helpers';
import { cleanUp, named, pick } from './service-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-SERVICE-SETUP-HOOKS';
const STEP = 'service.catalog';
/** Taxes' factory category every service of the run is charged with. */
const TAX = 'service.generic';
/** The hub's own services on offer, archived while the run needs a catalogue with nothing to charge. */
const PARKED = 'e2e_fix_service_hooks_parked';

test.beforeAll(() => {
  cleanUp();
  psql(
    [
      `drop table if exists ${PARKED}`,
      `create table ${PARKED} as select id from service_service where is_active`,
      `update service_service set is_active = false where id in (select id from ${PARKED})`,
    ].join('; '),
  );
});

test.afterAll(() => {
  try {
    cleanUp();
  } finally {
    psql([`update service_service set is_active = true where id in (select id from ${PARKED})`, `drop table ${PARKED}`].join('; '));
  }
});

/**
 * The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home, with
 * the instant of every `/api/live` the page opens: a new stream brings every result again, so a step that changes
 * without one came over the stream already open, re-run by its events.
 */
async function spanishOwner(
  browser: Browser,
  viewport: { width: number; height: number },
): Promise<{ context: BrowserContext; page: Page; streams: number[] }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  const streams: number[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/live')) streams.push(Date.now());
  });
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page, streams };
}

/** Waits until the page has opened no `/api/live` for a second: every subscription of the screen is declared. */
async function settled(streams: number[]): Promise<void> {
  await expect.poll(() => Date.now() - (streams.at(-1) ?? 0), { timeout: 15_000 }).toBeGreaterThan(1_000);
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const step = (page: Page): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);
const pill = (page: Page): Locator => step(page).locator('[data-testid="setup-pill"]');
const configure = (page: Page): Locator => step(page).locator(`[data-testid="setup-configure-${STEP}"]`);

/** «Ver todo»: a step below a more important pending one, or a done one, may be folded. */
async function unfolded(page: Page): Promise<void> {
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
  await expect(step(page)).toBeVisible();
}

/** A service of this run by the API as the owner (SERVICE-F01 has its own e2e), at a closed price. */
async function newService(context: BrowserContext, name: string): Promise<string> {
  const created = await api<{ id: string }>(context, A, 'POST', '/service/services', { name, price: 1800, duration_minutes: 30, tax_category_key: TAX });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  return created.data.id;
}

/** Archives (SERVICE-F04) or restores (SERVICE-F05) a service by the API as the owner. */
async function offer(context: BrowserContext, id: string, action: 'archive' | 'restore'): Promise<void> {
  const changed = await api(context, A, 'POST', `/service/services/${action}`, { id });
  expect(changed.status, JSON.stringify(changed.data)).toBe(200);
}

test(`${KEY} SERVICE-F01: «Tu catálogo de servicios» pending with nothing to charge, it leads to Services, the first service ticks it, archived it is pending again and restored done`, async ({
  browser,
}) => {
  const { context, page, streams } = await spanishOwner(browser, { width: 1440, height: 900 });
  const name = named('Corte');
  try {
    // The old module's item, same words, «Importante», while no service can be charged.
    await unfolded(page);
    await expect(step(page).locator('.setup-row-title')).toHaveText('Tu catálogo de servicios');
    await expect(step(page).locator('.setup-row-desc')).toHaveText('Añade los servicios que vendes, con su precio y su duración.');
    await expect(pill(page)).toHaveText('Importante');

    // «Configurar» leads to Services, where «Nuevo servicio» adds the first one at a closed price («Precio fijo»).
    await configure(page).click();
    await expect(page).toHaveURL(`${A}/service/services`);
    const view = shown(page);
    await view.locator('[data-testid=service-services-empty], [data-testid=service-services-row]').first().waitFor({ state: 'visible' });
    await view.locator('[data-testid=service-services-add]').click();
    const form = page.locator('ion-modal[data-testid=service-form]');
    await expect(form).toBeVisible();
    await form.locator('[data-testid=service-form-name] input').fill(name);
    await form.locator('[data-testid=service-form-price] input').fill('18,00');
    await form.locator('[data-testid=service-form-duration] input').fill('30');
    await pick(page, 'service-form-tax', 'general', 'Servicio — general');
    await form.locator('[data-testid=service-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(view.locator('[data-testid=service-services-row]', { hasText: name })).toBeVisible();
    const serviceId = psql(`select id from service_service where name = '${name}' and is_active`);
    expect(serviceId, 'the service was added on offer').toMatch(/^[0-9a-f-]{36}$/);

    // Back on the Home: done, with nothing left to configure.
    await page.goBack();
    await expect(page).toHaveURL(`${A}/`);
    await unfolded(page);
    await expect(pill(page)).toHaveText('Hecho');
    await expect(configure(page)).toHaveCount(0);

    // Archived, nothing can be charged: pending again without a reload, over the stream already open; restored, done.
    await settled(streams);
    const onTheHome = streams.length;
    await offer(context, serviceId, 'archive');
    await expect(pill(page)).toHaveText('Importante');
    await expect(configure(page)).toBeVisible();
    await offer(context, serviceId, 'restore');
    await expect(pill(page)).toHaveText('Hecho');
    expect(streams.length, 'the service archived and restored reached the Home without a new /api/live').toBe(onTheHome);
  } finally {
    await context.close();
    cleanUp();
  }
});

for (const size of VIEWPORTS) {
  test(`${KEY} SERVICE-F01 at ${size.label}: «Tu catálogo de servicios» pending in sight, then done without a reload once a service is added`, async ({
    browser,
  }) => {
    const { context, page, streams } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      await unfolded(page);
      await expect(pill(page)).toHaveText('Importante');
      await step(page).evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await untilStill(page);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });

      // A service added elsewhere (another device, the assistant): the step is done over the stream already open.
      await settled(streams);
      const onTheHome = streams.length;
      await newService(context, named(`Tinte ${size.label}`));
      await unfolded(page);
      await expect(pill(page)).toHaveText('Hecho');
      expect(streams.length, 'the service added reached the Home without a new /api/live').toBe(onTheHome);
    } finally {
      await context.close();
      cleanUp();
    }
  });
}

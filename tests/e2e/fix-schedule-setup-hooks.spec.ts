// flow: SCHEDULE-F03 SCHEDULE-F02
// Schedules' hook of the Home (FIX-SCHEDULE-SETUP-HOOKS; the old module's own `setup` item «Confirma tu horario»,
// schedules#42; the old hub's dashboard in docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads it in
// Spanish: «Confirma tu horario» pending and «Recomendado» in «Termina de configurar tu negocio» while the week is the
// default one, its «Configurar» leading to Schedules → Hours, where «Sí, este es mi horario» confirms it; then «Hecho»,
// and, with the default week back, «Hecho» again without a reload when a day of it is saved elsewhere. In each of the
// three sizes, the capture `FIX-SCHEDULE-SETUP-HOOKS-<width>` with the step pending in sight. The week and the settings
// the hub had before the file are put back after it (`afterAll`).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, login, psql, shown } from './helpers';
import { DEFAULT_WEEK, restoreWeek, snapshotWeek, VIEWPORTS, weekReady } from './schedule-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-SCHEDULE-SETUP-HOOKS';
const STEP = 'schedule.hours';

/** What the hub had before this file: its rows as INSERT statements, read in `beforeAll`. */
let before: string[] = [];

test.beforeAll(() => {
  before = snapshotWeek();
});

test.afterAll(() => {
  restoreWeek(before);
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

/** «Ver todo»: a «Recomendado» step, or a done one, is folded while more important ones are pending. */
async function unfolded(page: Page): Promise<void> {
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
  await expect(step(page)).toBeVisible();
}

/** Saves a day of the week by the API as the owner (SCHEDULE-F02 has its own e2e): Tuesday from 10:00 to 20:00. */
async function saveADay(context: BrowserContext): Promise<void> {
  const saved = await api(context, A, 'POST', '/schedule/week/set_day', {
    weekday: 1,
    intervals: [{ open_time: '10:00', close_time: '20:00' }],
  });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
}

test(`${KEY} SCHEDULE-F03: «Confirma tu horario» pending with the default week, it leads to Hours, «Sí, este es mi horario» ticks it, and a day saved elsewhere ticks it over the stream already open`, async ({
  browser,
}) => {
  psql(DEFAULT_WEEK);
  const { context, page, streams } = await spanishOwner(browser, { width: 1440, height: 900 });
  try {
    // The old module's item, same words, «Recomendado», while the week is the default one.
    await unfolded(page);
    await expect(step(page).locator('.setup-row-title')).toHaveText('Confirma tu horario');
    await expect(step(page).locator('.setup-row-desc')).toHaveText(
      'Hemos puesto un horario por defecto por ti (de lunes a viernes, de 09:00 a 18:00). Si coincide con el de tu ' +
        'negocio, confírmalo de un toque; si no, edita los días que cambien: las reservas fuera de tu horario se rechazan.',
    );
    await expect(pill(page)).toHaveText('Recomendado');

    // «Configurar» leads to Schedules → Hours, where the yellow notice's «Sí, este es mi horario» confirms the week.
    await configure(page).click();
    await expect(page).toHaveURL(`${A}/schedule/hours`);
    await weekReady(page);
    const notice = shown(page).locator('[data-testid=schedule-hours-default-week]');
    await expect(notice).toBeVisible();
    const confirm = notice.locator('[data-testid=schedule-hours-confirm-week]');
    await expect(confirm).toHaveText('Sí, este es mi horario');
    await confirm.click();
    await expect(notice).toHaveCount(0);
    expect(psql('select hours_confirmed from schedule_schedulesettings'), 'the week was confirmed').toBe('t');

    // Back on the Home: done, with nothing left to configure.
    await page.goBack();
    await expect(page).toHaveURL(`${A}/`);
    await unfolded(page);
    await expect(pill(page)).toHaveText('Hecho');
    await expect(configure(page)).toHaveCount(0);

    // The default week back (by the database's own hand, no notice): pending once the Home is read again.
    psql(DEFAULT_WEEK);
    await page.reload();
    await unfolded(page);
    await expect(pill(page)).toHaveText('Recomendado');

    // A day saved elsewhere (another device, the assistant) confirms the week too: done without a reload, over the
    // stream already open.
    await settled(streams);
    const onTheHome = streams.length;
    await saveADay(context);
    await expect(pill(page)).toHaveText('Hecho');
    await expect(configure(page)).toHaveCount(0);
    expect(streams.length, 'the day saved reached the Home without a new /api/live').toBe(onTheHome);
  } finally {
    await context.close();
  }
});

for (const size of VIEWPORTS) {
  test(`${KEY} SCHEDULE-F03 at ${size.label}: «Confirma tu horario» pending in sight, then done without a reload once the week is confirmed`, async ({
    browser,
  }) => {
    psql(DEFAULT_WEEK);
    const { context, page, streams } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      await unfolded(page);
      await expect(pill(page)).toHaveText('Recomendado');
      await step(page).evaluate((element) => element.scrollIntoView({ block: 'center' }));
      expect(await horizontalOverflow(page), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await capture(page, `${KEY}-${size.label}`);

      // The week confirmed elsewhere (another device, the assistant): the step is done over the stream already open.
      await settled(streams);
      const onTheHome = streams.length;
      const confirmed = await api(context, A, 'POST', '/schedule/week/confirm', {});
      expect(confirmed.status, JSON.stringify(confirmed.data)).toBe(200);
      await unfolded(page);
      await expect(pill(page)).toHaveText('Hecho');
      expect(streams.length, 'the week confirmed reached the Home without a new /api/live').toBe(onTheHome);
    } finally {
      await context.close();
    }
  });
}

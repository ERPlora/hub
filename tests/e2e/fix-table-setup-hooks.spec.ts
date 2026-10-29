// flow: TABLE-F02 TABLE-F01
// Tables' hook of the Home (FIX-TABLE-SETUP-HOOKS; the old module's own `setup` item «Tus mesas», tables#24; the old
// hub's dashboard in docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads it in Spanish: «Tus mesas»
// pending and «Recomendado» in «Termina de configurar tu negocio» while no table of the room is in use, its
// «Configurar» leading to Tables → Tables, where the first table is added in its zone; then «Hecho», and back to
// pending without a reload when that table is switched off. In each of the three sizes, the capture
// `FIX-TABLE-SETUP-HOOKS-<width>` with the step pending in sight. The tables the hub already had in use are switched
// off for the run and back on after it; the run's own zones are «E2E Tsh …», deleted with their tables before and after.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, login, psql, shot, shown, untilStill } from './helpers';
import { VIEWPORTS } from './inventory-helpers';
import { stamp } from './sale-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-TABLE-SETUP-HOOKS';
const STEP = 'table.tables';
const TAG = 'E2E Tsh';
/** The hub's own tables in use, switched off while the run needs a room without any. */
const PARKED = 'e2e_fix_table_hooks_parked';

function cleanUp(): void {
  const zones = `select id from table_zone where name like '${TAG} %'`;
  psql([`delete from table_table where zone_id in (${zones})`, `delete from table_zone where id in (${zones})`].join('; '));
}

test.beforeAll(() => {
  cleanUp();
  psql(
    [
      `drop table if exists ${PARKED}`,
      `create table ${PARKED} as select id from table_table where is_active and not is_deleted`,
      `update table_table set is_active = false where id in (select id from ${PARKED})`,
    ].join('; '),
  );
});

test.afterAll(() => {
  try {
    cleanUp();
  } finally {
    psql([`update table_table set is_active = true where id in (select id from ${PARKED})`, `drop table ${PARKED}`].join('; '));
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

/** «Ver todo»: a «Recomendado» step, or a done one, is folded while more important ones are pending. */
async function unfolded(page: Page): Promise<void> {
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
  await expect(step(page)).toBeVisible();
}

/** A zone of this run (TABLE-F01 has its own e2e), by the API as the owner. */
async function newZone(context: BrowserContext, name: string): Promise<string> {
  const created = await api<{ id: string }>(context, A, 'POST', '/table/zones', { name });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  return created.data.id;
}

test(`${KEY} TABLE-F02: «Tus mesas» pending without tables, it leads to Tables, the first one ticks it and switched off it is pending again`, async ({
  browser,
}) => {
  const { context, page, streams } = await spanishOwner(browser, { width: 1440, height: 900 });
  const zone = `${TAG} ${stamp()} Salón`;
  try {
    // The old module's item, same words, «Recomendado», while no table is in use.
    await unfolded(page);
    await expect(step(page).locator('.setup-row-title')).toHaveText('Tus mesas');
    await expect(step(page).locator('.setup-row-desc')).toHaveText(
      'Añade las mesas de tu sala: sin ellas no hay comanda por mesa, ni dividir ni transferir.',
    );
    await expect(pill(page)).toHaveText('Recomendado');

    // A zone alone does not tick it.
    await newZone(context, zone);
    await expect(pill(page)).toHaveText('Recomendado');

    // «Configurar» leads to Tables → Tables, where «+» adds the first table in the zone.
    await configure(page).click();
    await expect(page).toHaveURL(`${A}/table/tables`);
    const view = shown(page);
    await view.locator('[data-testid="table-tables-add"]').click();
    const form = page.locator('ion-modal[data-testid=table-form]');
    await expect(form).toBeVisible();
    await form.locator('[data-testid=table-form-number] input').fill('1');
    await form.locator('[data-testid=table-form-zone]').click();
    await page.locator('ion-popover').getByText(zone, { exact: true }).click();
    await form.locator('[data-testid=table-form-submit]').click();
    await expect(form).toBeHidden();
    const tableId = psql(`select t.id from table_table t join table_zone z on z.id = t.zone_id where z.name = '${zone}' and t.number = '1'`);
    expect(tableId, 'the table was added in the zone of the run').toMatch(/^[0-9a-f-]{36}$/);

    // Back on the Home: done, with nothing left to configure.
    await page.goBack();
    await expect(page).toHaveURL(`${A}/`);
    await unfolded(page);
    await expect(pill(page)).toHaveText('Hecho');
    await expect(configure(page)).toHaveCount(0);

    // Switched off, the room has no table in use: pending again without a reload, over the stream already open.
    await settled(streams);
    const onTheHome = streams.length;
    const off = await api(context, A, 'POST', '/table/tables/update', { id: tableId, is_active: false });
    expect(off.status, JSON.stringify(off.data)).toBe(200);
    await expect(pill(page)).toHaveText('Recomendado');
    await expect(configure(page)).toBeVisible();
    expect(streams.length, 'the table switched off reached the Home without a new /api/live').toBe(onTheHome);
  } finally {
    await context.close();
    cleanUp();
  }
});

for (const size of VIEWPORTS) {
  test(`${KEY} TABLE-F02 at ${size.label}: «Tus mesas» pending in sight, then done without a reload once a table is added`, async ({
    browser,
  }) => {
    const { context, page, streams } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      await unfolded(page);
      await expect(pill(page)).toHaveText('Recomendado');
      await step(page).evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await untilStill(page);
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });

      // A table in a zone of the run, added elsewhere (another device): the step is done over the stream already open.
      const zoneId = await newZone(context, `${TAG} ${stamp()} Terraza`);
      await settled(streams);
      const onTheHome = streams.length;
      const created = await api(context, A, 'POST', '/table/tables', { zone_id: zoneId, number: '1' });
      expect(created.status, JSON.stringify(created.data)).toBe(201);
      await unfolded(page);
      await expect(pill(page)).toHaveText('Hecho');
      expect(streams.length, 'the table added reached the Home without a new /api/live').toBe(onTheHome);
    } finally {
      await context.close();
      cleanUp();
    }
  });
}

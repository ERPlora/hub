// flow: BASE-F35, BASE-F36, BASE-F31 — a backup of the business takes what Reservations, Automations, Tasks and Kitchen
// have, on hub `a`: in Settings › Data › Export each of their rows shows its parts with their rows, and an app whose data
// does not travel (Time clock) says «Its data does not travel in the file» instead of «Nothing of its own to copy». The
// file downloaded carries the time slot, the automation, the project with its open task and the station with the
// product routed to it; loaded again from Import once they are deleted, they come back, the automation paused. Each
// screen in the three sizes, and in Spanish. Its data are named `E2E Copy …` / `E2E-COPY-…` / `e2e-copy-…`, its slot
// starts at 03:17, and `afterAll` deletes exactly them.
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, ARTIFACTS, capture, horizontalOverflow, hostPage, psql, shown, signedInSpanish, testid, THREE_SIZES, untilStill } from './helpers';

test.use({ actionTimeout: 30_000 });

const STAMP = Date.now().toString(36).toUpperCase();
const SKU = `E2E-COPY-${STAMP}`;
const PRODUCT = `E2E Copy Burger ${STAMP}`;
const FLOW = `E2E Copy Flow ${STAMP}`;
const PROJECT = `e2e-copy-${STAMP.toLowerCase()}`;
const TASK = `E2E Copy Task ${STAMP}`;
const STATION = `E2E Copy Grill ${STAMP}`;
const SLOT = { day_of_week: 6, start_time: '03:17', end_time: '03:47', max_reservations: 1 };

/** The rows of Export each app shows with its data ticked: the part and its label, in English and in Spanish. */
const PARTS = {
  reservation: { part: 'reservation.time_slot', en: 'Booking time slots', es: 'Franjas de reserva' },
  flow: { part: 'flow.flow', en: 'Automations', es: 'Automatizaciones' },
  task: { part: 'task.task', en: 'Open tasks', es: 'Tareas abiertas' },
  kitchen: { part: 'kitchen.station', en: 'Stations', es: 'Estaciones' },
} as const;
type App = keyof typeof PARTS;
const STAYS = 'attendance';

interface Listed<T> {
  rows: T[];
}
interface Row {
  id: string;
  name?: string;
  title?: string;
  code?: string;
  start_time?: string;
  enabled?: boolean;
  target_name?: string;
  target_id?: string;
  station_name?: string;
}

function cleanUp(): void {
  psql(
    [
      "delete from kitchen_productroute where station_id in (select id from kitchen_station where name like 'E2E Copy %')",
      "delete from kitchen_station where name like 'E2E Copy %'",
      "delete from task_task where title like 'E2E Copy %'",
      "delete from task_project where code like 'e2e-copy-%'",
      "delete from flow_flow where name like 'E2E Copy %'",
      "delete from reservation_timeslot where start_time = '03:17'",
      "delete from inventory_stockmovement where product_id in (select id from inventory_product where sku like 'E2E-COPY-%')",
      "delete from inventory_product where sku like 'E2E-COPY-%'",
    ].join('; '),
  );
}

async function rows(context: BrowserContext, path: string): Promise<Row[]> {
  const page = await api<Listed<Row>>(context, A, 'GET', `${path}?limit=100`);
  expect(page.status).toBe(200);
  return page.data.rows;
}

async function mine(context: BrowserContext): Promise<{ slot?: Row; flow?: Row; task?: Row; project?: Row; station?: Row; route?: Row }> {
  return {
    slot: (await rows(context, '/reservation/time_slots')).find((row) => row.start_time?.startsWith('03:17')),
    flow: (await rows(context, '/flow/flows')).find((row) => row.name === FLOW),
    task: (await rows(context, '/task/tasks')).find((row) => row.title === TASK),
    project: (await rows(context, '/task/projects')).find((row) => row.code === PROJECT),
    station: (await rows(context, '/kitchen/stations')).find((row) => row.name === STATION),
    route: (await rows(context, '/kitchen/routing')).find((row) => row.station_name === STATION),
  };
}

async function make(context: BrowserContext): Promise<void> {
  if ((await mine(context)).station) return;
  const product = await api<Row>(context, A, 'POST', '/inventory/products', { name: PRODUCT, sku: SKU, price: 900, tax_category_key: 'restaurant.food' });
  expect(product.status).toBe(201);
  expect((await api(context, A, 'POST', '/reservation/time_slots', SLOT)).status).toBe(201);
  expect((await api(context, A, 'POST', '/flow/flows', { name: FLOW, trigger: { kind: 'manual' }, steps: [] })).status).toBe(201);
  expect((await api(context, A, 'POST', '/task/projects', { code: PROJECT, name: `E2E Copy Opening ${STAMP}` })).status).toBe(201);
  expect((await api(context, A, 'POST', '/task/tasks', { title: TASK, project: PROJECT, priority: 'high' })).status).toBe(201);
  expect((await api(context, A, 'POST', '/kitchen/stations', { name: STATION })).status).toBe(201);
  expect((await api(context, A, 'POST', '/kitchen/routing', { station: STATION, product_id: product.data.id })).status).toBe(200);
}

async function removeMine(context: BrowserContext): Promise<void> {
  const now = await mine(context);
  expect((await api(context, A, 'POST', '/kitchen/routing/clear', { product_id: now.route?.target_id })).status).toBe(200);
  expect((await api(context, A, 'POST', '/kitchen/stations/delete', { station_id: now.station?.id })).status).toBe(200);
  expect((await api(context, A, 'POST', '/task/tasks/delete', { id: now.task?.id })).status).toBe(200);
  expect((await api(context, A, 'POST', '/task/projects/delete', { id: now.project?.id })).status).toBe(200);
  expect((await api(context, A, 'POST', '/flow/flows/delete', { id: now.flow?.id })).status).toBe(200);
  expect((await api(context, A, 'POST', '/reservation/time_slots/delete', { id: now.slot?.id })).status).toBe(200);
}

async function snap(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

/** Settings › Data › Export: each app of the spec shows its parts with their rows once its data is ticked, and Time
 *  clock says that its data does not travel. */
async function partsOf(context: BrowserContext, page: Page, language: 'en' | 'es', stays: string): Promise<void> {
  await make(context);
  await page.goto(`${A}/settings?data=export#data`);
  for (const app of Object.keys(PARTS) as App[]) {
    await expect(shown(page).locator(`[data-testid="export-app"][data-id="${app}"]`)).toBeVisible();
    await testid(page, `export-data-${app}`).click();
    await expect(shown(page).locator(`[data-testid="export-table-${PARTS[app].part}"]`)).toContainText(`${PARTS[app][language]} ·`);
  }
  const attendance = shown(page).locator(`[data-testid="export-app"][data-id="${STAYS}"]`);
  await expect(attendance).toContainText(stays);
  await attendance.scrollIntoViewIfNeeded();
}

/** The rows of `part` the file `saved` carries. */
function rowsIn(saved: string, part: string): Record<string, unknown>[] {
  return JSON.parse(execFileSync('unzip', ['-p', saved, `data/${part}.json`], { encoding: 'utf8' }));
}

test.beforeAll(() => cleanUp());
test.afterAll(() => cleanUp());

for (const size of THREE_SIZES) {
  test(`a backup takes the slots, automations, tasks and stations and brings them back at ${size.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await hostPage(browser, A, { viewport: { width: size.width, height: size.height }, next: '/settings#data' });
    await partsOf(context, page, 'en', 'Its data does not travel in the file');
    await expect(shown(page).locator(`[data-testid="export-app"][data-id="${STAYS}"]`)).not.toContainText('Nothing of its own to copy');
    await snap(page, `BASE-F36-backup-more-apps-${size.label}`);

    const [download] = await Promise.all([page.waitForEvent('download'), testid(page, 'export-submit').click()]);
    const saved = join(ARTIFACTS, `backup-more-apps-${size.label}-${download.suggestedFilename()}`);
    await download.saveAs(saved);
    expect(rowsIn(saved, 'reservation.time_slot')).toContainEqual(expect.objectContaining({ start_time: '03:17', end_time: '03:47' }));
    expect(rowsIn(saved, 'flow.flow')).toContainEqual(expect.objectContaining({ name: FLOW }));
    expect(rowsIn(saved, 'task.project')).toContainEqual(expect.objectContaining({ code: PROJECT }));
    expect(rowsIn(saved, 'task.task')).toContainEqual(expect.objectContaining({ title: TASK, project: PROJECT, priority: 'high' }));
    expect(rowsIn(saved, 'kitchen.station')).toContainEqual(expect.objectContaining({ name: STATION, products: [PRODUCT] }));

    await removeMine(context);
    await testid(page, 'data-section-import').click();
    await testid(page, 'import-file').setInputFiles(saved);
    await expect(testid(page, 'review')).toBeVisible();
    await testid(page, 'review-import').click();
    for (const app of Object.keys(PARTS)) {
      const loaded = shown(page).locator(`[data-testid="report-app"][data-id="${app}"] [data-testid="report-app-status"]`);
      await expect(loaded).toContainText('Applied');
    }
    await shown(page).locator('[data-testid="report-app"][data-id="reservation"]').scrollIntoViewIfNeeded();
    await snap(page, `BASE-F31-backup-more-apps-back-${size.label}`);

    const back = await mine(context);
    expect([back.slot?.start_time?.slice(0, 5), back.flow?.enabled, back.task?.title, back.project?.code]).toEqual(['03:17', false, TASK, PROJECT]);
    expect([back.station?.name, back.route?.target_name]).toEqual([STATION, PRODUCT]);
    await context.close();
  });

  test(`in Spanish, the parts say «Franjas de reserva» and «Tareas abiertas» and Fichaje says its data stay at ${size.label}`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, { width: size.width, height: size.height }, '/settings#data');
    await partsOf(context, page, 'es', 'Sus datos no viajan en el archivo');
    await snap(page, `BASE-F36-backup-more-apps-es-${size.label}`);
    await context.close();
  });
}

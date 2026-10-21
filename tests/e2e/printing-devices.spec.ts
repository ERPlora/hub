// Printing → Devices in Chrome (PRINTING-F18; apps/printing/WORKBOOK.md; FIX-PRINTING-JOBS-CLAIMED-BY-ANY-DEVICE):
// an employee's session took the jobs of any printer by naming it. Now the owner sets up the browser's device
// from Devices («Print from this device», with its printer), the list marks it as this device and the note says
// what it prints; the employee's session takes the jobs only from that device (by the API, the device's side of
// /ws/print), never from another, and once the owner retires it, not from it either. The employee reads the page
// without setting anything up. Screenshots of the flow in the three viewports. What is made here is deleted
// after it.
// flow: PRINTING-F18
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, hostPage, login, psql, shot, shown } from './helpers';
import { dialog, fill } from './inventory-helpers';
import { FLOW_VIEWPORTS, flowShots, forgetDevices } from './printing-helpers';
import { stamp } from './sale-helpers';

test.describe.configure({ mode: 'serial' });

const RUN = stamp();
const PRINTER = `e2e Dev ${RUN}`;
const DEVICE_NAME = `e2e Counter ${RUN}`;
/** Another device's own id: never set up here. */
const STRANGER = `e2e stranger ${RUN}`;

interface Device {
  id: string;
  name: string;
  this_device: boolean;
  printers: { id: string; name: string }[];
}

test.afterAll(() => {
  psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like 'e2e Dev %')`);
  forgetDevices('e2e Dev %', { ids: [STRANGER], names: ['e2e Counter %'] });
  psql(`delete from printing_printer where name like 'e2e Dev %'`);
});

async function devicesReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-devices-row], [data-testid=printing-devices-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=printing-devices-this]').waitFor({ state: 'visible' });
}

/** The id the SPA names this browser's device with (`X-Device-Id`): what the app of the device would say. */
async function browserDevice(page: Page): Promise<string> {
  const id = await page.evaluate(() => window.localStorage.getItem('erplora.device_id'));
  expect(id, 'the SPA keeps its device id').toMatch(/^[0-9a-f-]{36}$/);
  return id!;
}

async function claimAs(context: BrowserContext, printer: string, device: string) {
  return api<{ job: { id: string } | null; error?: { code: string } }>(context, A, 'POST', '/printing/jobs/claim', { printers: [printer], device });
}

async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const hook = `printing-devices-row-${id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=printing-devices-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

test('PRINTING-F18: only the device the owner set up takes the queue, with anybody’s session', async ({ page, context, browser }) => {
  await login(page, A, '/printing/devices');
  const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
    name: PRINTER,
    kind: 'network',
    address: '10.0.0.88',
    usage: 'receipt',
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  const printer = created.data.id;
  const mine = await browserDevice(page);

  // The employee's session, on a device nobody set up: refused, and the job stays waiting (the bug).
  const employee = await hostPage(browser, A, { next: '/printing/devices', credentials: EMPLOYEE });
  const queued = await api<{ id: string }>(context, A, 'POST', '/printing/printers/test', { printer_id: printer });
  expect(queued.status).toBe(201);
  const refused = await claimAs(employee.context, printer, mine);
  expect([refused.status, refused.data.error?.code]).toEqual([403, 'printing.device_not_registered']);

  // The owner sets this browser's device up from Devices.
  await devicesReady(page);
  await expect(shown(page).locator('[data-testid=printing-devices-this]')).toContainText(/does not print yet|todavía no imprime/);
  await shown(page).locator('[data-testid=printing-devices-add]').click();
  const modal = dialog(page, 'printing-device');
  await expect(modal).toBeVisible();
  await fill(modal, 'printing-device-name', DEVICE_NAME);
  await modal.locator(`[data-testid=printing-device-printer-${printer}]`).click();
  await flowShots(page, 'PRINTING-F18-DEVICE', async () => {
    await expect(modal.locator('[data-testid=printing-device-submit]')).toBeVisible();
  });
  await modal.locator('[data-testid=printing-device-submit]').click();
  await expect(modal).toBeHidden();
  const row = shown(page).locator('[data-testid=printing-devices-row]').filter({ hasText: DEVICE_NAME });
  await expect(row).toContainText(/This device|Este dispositivo/);
  await expect(row).toContainText(PRINTER);
  await expect(shown(page).locator('[data-testid=printing-devices-this]')).toContainText(new RegExp(`(prints for|imprime para): ${PRINTER}\\.`));
  await expect(shown(page).locator('[data-testid=printing-devices-add]')).toHaveCount(0);
  // «This device prints now.» said, the toast goes before the screenshots: it would cover the tabbar.
  await page.locator('ion-toast').evaluateAll((toasts) => Promise.all(toasts.map((toast) => (toast as unknown as { dismiss: () => Promise<boolean> }).dismiss())));
  await expect(page.locator('ion-toast')).toHaveCount(0);
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await devicesReady(page);
    await expect(shown(page).locator('[data-testid=printing-devices-row]').filter({ hasText: DEVICE_NAME })).toBeVisible();
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: shot(`FIX-PRINTING-JOBS-CLAIMED-BY-ANY-DEVICE-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });

  // From now on the employee's session takes the job from this device, and from no other.
  const stranger = await claimAs(employee.context, printer, STRANGER);
  expect([stranger.status, stranger.data.error?.code]).toEqual([403, 'printing.device_not_registered']);
  const taken = await claimAs(employee.context, printer, mine);
  expect(taken.status, JSON.stringify(taken.data)).toBe(200);
  expect(taken.data.job?.id).toBe(queued.data.id);
  const foreign = await api<{ error?: { code: string } }>(employee.context, A, 'POST', '/printing/jobs/complete', {
    job_id: queued.data.id,
    device: STRANGER,
    attempt: 1,
  });
  expect([foreign.status, foreign.data.error?.code]).toEqual([409, 'printing.job_not_yours']);
  // The queue names the device by its name, never by its id (hub#2551).
  const jobs = await api<{ rows: { id: string; device: string }[] }>(employee.context, A, 'GET', `/printing/jobs?printer_id=${printer}`);
  expect(jobs.data.rows.map((job) => job.device)).toEqual([DEVICE_NAME]);
  expect(JSON.stringify(jobs.data)).not.toContain(mine);
  const done = await api<{ confirmed: boolean }>(employee.context, A, 'POST', '/printing/jobs/complete', {
    job_id: queued.data.id,
    device: mine,
    attempt: 1,
  });
  expect(done.data.confirmed).toBe(true);

  // Retired, it takes nothing more: not even with the owner's session.
  const listed = await api<{ rows: Device[] }>(context, A, 'GET', '/printing/devices');
  const set = listed.data.rows.find((device) => device.name === DEVICE_NAME)!;
  await rowAction(page, set.id, 'retire');
  await page.locator('ion-modal').getByRole('button', { name: /Yes, retire|Sí, retirar/ }).click();
  await expect(row).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=printing-devices-add]')).toBeVisible();
  await api(context, A, 'POST', '/printing/printers/test', { printer_id: printer });
  for (const who of [employee.context, context]) {
    const after = await claimAs(who, printer, mine);
    expect([after.status, after.data.error?.code]).toEqual([403, 'printing.device_not_registered']);
  }
  await employee.context.close();
});

test('PRINTING-F18: the employee reads the devices and sets none up', async ({ page }) => {
  await login(page, A, '/printing/devices', EMPLOYEE);
  await devicesReady(page);
  await expect(shown(page).locator('[data-testid=printing-devices-heading]')).toHaveText(/Devices that print|Dispositivos que imprimen/);
  await expect(shown(page).locator('[data-testid=printing-devices-this]')).toContainText(/someone who manages the printers|quien gestiona las impresoras/);
  await expect(shown(page).locator('[data-testid=printing-devices-add]')).toHaveCount(0);
});

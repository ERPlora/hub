// flow: PRINTING-F01
// Printing's hooks of the Home, the step «Configura la impresora» and the bell's «Nadie está imprimiendo «…»», as
// the owner of hub `a` reads them in Spanish: «Configura la impresora» pending and «Recomendado» in «Termina de
// configurar tu negocio» while no device set up prints the receipts, its «Configurar» leading to Printing → Devices; a
// receipt queued on a receipt printer no device reaches rings the bell without a reload once it has waited a minute
// (`psql()` moves it back; the bell reads the clock every 30 s), its notice «Nadie está imprimiendo «Recibo»: N
// trabajos esperando» leads with «Ver las impresoras» to Printing → Printers, whose receipts' card says «Sin
// dispositivo» and where to set one up; the device set up from it quiets the bell and the card and ticks the step,
// live; retired, the step is pending again. In each of the three sizes, leaving a capture with the action center open.
// What it makes is «e2e Hooks …», deleted before and after; the devices set up before it are parked (retired) for the
// run and put back after it.
import { type BrowserContext, expect, test } from '@playwright/test';

import { bellSays, bellTotal, featureNotice, noticeButton } from './action-center';
import { A, api, capturedFitting, login, psql, shown } from './helpers';
import { setupStep } from './home-helpers';
import { liveStreamsSettled, spanishOwner } from './live-streams';
import { FLOW_VIEWPORTS, forgetDevices } from './printing-helpers';
import { stamp } from './sale-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-PRINTING-SETUP-HOOKS';
const STEP = 'printing.printer';
const ROW = 'printing.stalled_receipt';
const TAG = 'e2e Hooks';
const RUN = stamp();
/** The devices set up before this file: retired with this mark for the run, back after it. */
const PARKED = 'e2e-fix-printing-hooks-parked';

function cleanUp(): void {
  psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like '${TAG} %')`);
  forgetDevices(`${TAG} %`, { names: [`${TAG} %`] });
  psql(`delete from printing_printer where name like '${TAG} %'`);
}

/** The receipt printer of this run: a network one no device reaches yet. */
let printer = '';

test.beforeAll(async ({ browser }) => {
  cleanUp();
  psql(`update printing_printdevice set retired_at = now(), retired_by = '${PARKED}' where retired_at is null`);
  const context = await browser.newContext({ baseURL: A });
  try {
    await login(await context.newPage(), A, '/printing/printers');
    const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
      name: `${TAG} Till ${RUN}`,
      kind: 'network',
      address: '10.0.0.77',
      usage: 'receipt',
    });
    expect(created.status, JSON.stringify(created.data)).toBe(201);
    printer = created.data.id;
  } finally {
    await context.close();
  }
});

test.afterAll(() => {
  try {
    cleanUp();
  } finally {
    psql(`update printing_printdevice set retired_at = null, retired_by = '' where retired_by = '${PARKED}'`);
  }
});

/** How many receipts wait with nobody printing them now, as the server says (`printing.stalled_receipt`). */
async function stalledNow(context: BrowserContext): Promise<number> {
  const res = await api<{ counters: { key: string; count: number }[] }>(context, A, 'GET', '/home/bell');
  expect(res.status).toBe(200);
  return res.data.counters.find((counter) => counter.key === ROW)?.count ?? 0;
}

/** Sets up the device `device` with this run's printer, from the device (its `X-Device-Id`), as Devices does. */
async function setUpDevice(context: BrowserContext, device: string): Promise<string> {
  const host = new URL(A).hostname;
  const csrf = (await context.cookies(A)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const res = await context.request.post(`${A}/api/printing/devices`, {
    headers: { 'X-CSRFToken': csrf, Accept: 'application/json', 'X-Device-Id': device },
    data: { name: `${TAG} Counter ${RUN}`, printers: [printer] },
  });
  expect(res.status(), await res.text()).toBe(201);
  return ((await res.json()) as { id: string }).id;
}

/** The operations Printing → Devices subscribes, which the Home does not. */
const DEVICES_OPS = ['printing.device.list', 'printing.printer.list'];

const { row: step, pill, unfolded } = setupStep(STEP);
/** The notice's title, in the singular for one job. */
const stalledTitle = (count: number): string =>
  `Nadie está imprimiendo «Recibo»: ${count === 1 ? '1 trabajo esperando' : `${count} trabajos esperando`}`;
const STALLED = /Nadie está imprimiendo «Recibo»: \d+ trabajos? esperando/;

FLOW_VIEWPORTS.forEach(({ label, width, height }) => {
  test(`PRINTING-F01: «Configura la impresora» and «Nadie está imprimiendo «Recibo»» on the Home, live — ${label}`, async ({
    browser,
  }) => {
    const { context, page, streams } = await spanishOwner(browser, { width, height });
    const device = `${TAG} device ${RUN} ${label}`;
    let deviceId = '';
    try {
      // The step, as the old core item said it, pending while no device set up prints the receipts.
      await unfolded(page);
      await expect(step(page).locator('.setup-row-title')).toHaveText('Configura la impresora');
      await expect(step(page).locator('.setup-row-desc')).toHaveText(
        'Da de alta el dispositivo que imprime los tiques de tus clientes, para que la primera venta salga en papel.',
      );
      await expect(pill(page)).toHaveText('Recomendado');
      // «Configurar» leads to where the device is set up.
      await step(page).locator(`[data-testid="setup-configure-${STEP}"]`).click();
      await expect(page).toHaveURL(`${A}/printing/devices`);
      await expect(shown(page).locator('[data-testid=printing-devices-this]')).toBeVisible();
      // Devices is live, as a person reads it: its subscriptions are on the stream before going back.
      await expect.poll(() => DEVICES_OPS.every((op) => streams.at(-1)?.ops.includes(op)), { timeout: 15_000 }).toBe(true);
      await page.goBack();
      await expect(page).toHaveURL(`${A}/`);
      await unfolded(page);

      // The Home as it is read: its stream settled before anything changes the bell.
      await liveStreamsSettled(streams, DEVICES_OPS);
      // Settled on the Home's own stream: Devices' subscriptions, released, ride on none of what the page has open.
      expect(DEVICES_OPS.filter((op) => streams.at(-1)?.ops.includes(op)), 'the Home settled with Devices released').toEqual([]);
      const [total, stalled] = await Promise.all([bellTotal(context), stalledNow(context)]);
      await bellSays(page, total);
      const onTheHome = streams.length;

      // A receipt queued on the till no device reaches: the bell rings without a reload, over the open stream.
      const queued = await api<{ job: { id: string } }>(context, A, 'POST', '/printing/jobs', {
        document_type: 'receipt',
        document: { business_name: 'e2e', receipt_id: `T-${RUN}`, items: [{ name: 'Haircut', quantity: 1, total: 18 }], total: 18 },
        job_key: `${TAG} ${RUN} ${label}`,
        printer,
      });
      expect(queued.status, JSON.stringify(queued.data)).toBe(201);
      // The bell counts what has waited a minute (the old hub's 60 s): the receipt waited 2 min.
      psql(`update printing_printjob set created_at = now() - interval '2 minutes' where id = '${queued.data.job.id}'`);
      await bellSays(page, total + 1, { timeout: 45_000 });
      expect(streams.length, 'the queued receipt reached the bell without a new /api/live').toBe(onTheHome);

      // The capture: the Home with the action center open, the notice naming the function as Printing does.
      const featured = await featureNotice(page, STALLED);
      await expect(featured.locator('h3')).toHaveText(stalledTitle(stalled + 1));
      const printers = noticeButton(featured, 'Ver las impresoras');
      await expect(printers).toBeVisible();
      await capturedFitting(page, `${KEY}-${label}`, label);

      // Its button leads to the printers, where the receipts' card says why and where to fix it.
      await printers.click();
      await expect(page).toHaveURL(`${A}/printing/printers`);
      const why = shown(page).locator('[data-testid=printing-summary-no-device-receipt]');
      await expect(why).toHaveText('Ningún dispositivo dado de alta lo imprime: dalo de alta en Dispositivos.');
      await expect(shown(page).locator('[data-testid=printing-summary-card-receipt]')).toContainText('Sin dispositivo');

      // The device set up with the till quiets the bell and the card, live.
      deviceId = await setUpDevice(context, device);
      await bellSays(page, total);
      await expect(why).toHaveCount(0);

      // Back on the Home, the step is done; the device retired, it is pending again without a reload.
      await page.goto(`${A}/`);
      await unfolded(page);
      await expect(pill(page)).toHaveText('Hecho');
      await expect(step(page).locator(`[data-testid="setup-configure-${STEP}"]`)).toHaveCount(0);
      const retired = await api(context, A, 'POST', '/printing/devices/retire', { device_id: deviceId });
      expect(retired.status).toBe(200);
      await expect(pill(page)).toHaveText('Recomendado');
      await bellSays(page, total + 1);
    } finally {
      await context.close();
      psql(`delete from printing_printjob where printer_id = '${printer}'`);
      forgetDevices(`${TAG} %`, { ids: [device] });
    }
  });
});

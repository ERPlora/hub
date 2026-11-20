// The assistant's card for a write of Printing (base's half is hub#416, BASE-F97): «cambia las impresoras de la tablet
// del mostrador», «reintenta el ticket» or «imprime la comanda» name every record as the Printing screens show it — a
// device and its printers by their names, a job as the queue titles it («Recibo …») —, read as the person, never by
// its id, also the ids its schema does not mark, and a document by the queue's word for it («Comanda de cocina»),
// never as the model sent it («kitchen_order»). End to end with the stack's SaaS gateway and
// the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this
// folder, «El asistente»). Cancelled, nothing changes. What this file creates carries its own prefix (E2E PAC) and goes
// away; the app it turns on is turned off again.
// flow: printing-assistant-card
// flow: PRINTING-F16 BASE-F97
import { randomUUID } from 'node:crypto';

import { type BrowserContext, expect, test } from '@playwright/test';

import { AN_ID, cardSpec } from './assistant-card-helpers';
import { askForACard, cancelAtComputerSize, cancelInSpanish, card, openPanelAtTheDesk, type SentCard, sentCard } from './assistant-panel';
import { A, api, capture, login, psql, THREE_SIZES as VIEWPORTS, untilStill } from './helpers';
import { forgetDevices } from './printing-helpers';

const KEY = 'FIX-HUB-PRINTING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
const NEEDED = ['printing'];
const PREFIX = 'E2E PAC';
const RUN = Date.now().toString(36).toUpperCase();
/** The document's number of the receipt this file queues: what the queue titles its job by. */
const NUMBER = `E2EPAC-${RUN}`;


/** Deletes what this file created: its receipt's jobs, its device and its printers (`E2E PAC …`). */
function cleanUp(): void {
  psql(
    `delete from printing_printjob where reference like 'E2EPAC-%' or printer_id in (select id from printing_printer where name like '${PREFIX} %')`,
  );
  forgetDevices(`${PREFIX} %`, { names: [`${PREFIX} %`] });
  psql(`delete from printing_printer where name like '${PREFIX} %'`);
}

cardSpec(NEEDED, cleanUp);

const said = (sent: SentCard): Record<string, unknown> => Object.fromEntries(sent.fields.map((field) => [field.name, field.value]));

async function made<T>(context: BrowserContext, path: string, body: unknown, headers: Record<string, string> = {}): Promise<T> {
  const host = new URL(A).hostname;
  const csrf = (await context.cookies(A)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const res = await context.request.post(`${A}/api${path}`, {
    headers: { 'X-CSRFToken': csrf, Accept: 'application/json', ...headers },
    data: body,
  });
  expect(res.status(), `${path}: ${await res.text()}`).toBe(201);
  return (await res.json()) as T;
}

type Printer = { id: string; name: string };

/** The owner, in Spanish, with the printers «E2E PAC Caja» and «E2E PAC Cocina», the device «E2E PAC Tablet del
 * mostrador» that reaches the till's, and a receipt in the queue: made through the app's own API. */
async function ownerWithAPrintingBusiness(browser: import('@playwright/test').Browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const printer = (name: string, usage: string, address: string) =>
    made<Printer>(context, '/printing/printers', { name: `${PREFIX} ${name} ${RUN}`, kind: 'network', address, usage });
  const till = await printer('Caja', 'receipt', '10.0.0.71');
  const kitchen = await printer('Cocina', 'kitchen', '10.0.0.72');
  const device = await made<{ id: string; name: string }>(
    context,
    '/printing/devices',
    { name: `${PREFIX} Tablet del mostrador ${RUN}`, printers: [till.id] },
    { 'X-Device-Id': randomUUID() },
  );
  const queued = await made<{ job: { id: string } }>(context, '/printing/jobs', {
    document_type: 'receipt',
    document: { receipt_id: NUMBER, items: [{ name: 'Corte', quantity: 1, total: 18 }], total: 18 },
    printer: till.id,
  });
  return { context, page, till, kitchen, device, job: queued.job };
}

test('printing-assistant-card — in Spanish changing a device’s printers, retrying a job and printing a kitchen order name the device, the printers, the job and the document, never by their id', async ({ browser }) => {
  const { context, page, till, kitchen, device, job } = await ownerWithAPrintingBusiness(browser);
  // The new reads answer over HTTP, as the card reads them.
  const read = await api<{ label: string }>(context, A, 'GET', `/printing/jobs/detail?job_id=${job.id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  expect(read.data.label).toBe(`Recibo ${NUMBER}`);
  await openPanelAtTheDesk(page);

  // «Que la tablet del mostrador imprima también por la de cocina»: the device and its printers by their names, as the
  // server sends them and as the card says them, one after another (never «Impresoras: 2 elementos»).
  let sent = sentCard(page);
  await askForACard(page, `E2E-ASK printing__device__update ${JSON.stringify({ device_id: device.id, printers: [till.id, kitchen.id] })}`);
  let fields = await sent;
  expect(said(fields)).toEqual({ device_id: device.name, printers: [till.name, kitchen.name] });
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Dispositivo: ${device.name}`);
    await expect(card(page)).toContainText(`Impresoras: ${till.name}, ${kitchen.name}`);
    await expect(card(page)).not.toContainText('elementos');
    await expect(card(page)).not.toContainText(AN_ID);
    await untilStill(page);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);

  // «Reintenta el ticket»: the job as the queue titles it, by the queue's word for a job.
  sent = sentCard(page);
  await askForACard(page, `E2E-ASK printing__job__retry ${JSON.stringify({ job_id: job.id })}`);
  fields = await sent;
  expect(fields.fields.find((field) => field.name === 'job_id')).toMatchObject({ value: `Recibo ${NUMBER}`, label: 'Trabajo' });
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  await expect(card(page)).toContainText(`Recibo ${NUMBER}`);
  await expect(card(page)).not.toContainText(AN_ID);
  await cancelInSpanish(page);

  // «Imprime la comanda de cocina»: the document by the queue's word, never «kitchen_order».
  sent = sentCard(page);
  await askForACard(page, `E2E-ASK printing__job__create ${JSON.stringify({ document_type: 'kitchen_order', document: { order_number: 'M-1' } })}`);
  expect(said(await sent).document_type).toBe('Comanda de cocina');
  await expect(card(page)).toContainText('Comanda de cocina');
  await expect(card(page)).not.toContainText('kitchen_order');
  await cancelInSpanish(page);

  // Cancelled, nothing changed: the device still reaches the till's printer only, and the receipt still waits.
  const devices = await api<{ rows: { id: string; printers: { id: string }[] }[] }>(context, A, 'GET', '/printing/devices');
  expect(devices.data.rows.find((row) => row.id === device.id)?.printers.map((p) => p.id)).toEqual([till.id]);
  const still = await api<{ status: string; attempts: number }>(context, A, 'GET', `/printing/jobs/detail?job_id=${job.id}`);
  expect([still.data.status, still.data.attempts]).toEqual(['pending', 0]);
  const queue = await api<{ total: number }>(context, A, 'GET', '/printing/jobs?search=M-1');
  expect(queue.data.total).toBe(0);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

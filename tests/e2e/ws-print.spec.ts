// The print host's channel, /ws/print, in Chrome (PLAN-HUB §5; base/ws_print.py). It answered 500: Django
// serves HTTP only. A page of the hub, signed in, opens the WebSocket the way the device's print host does,
// says hello with the printer it reaches, is woken when a job is queued (by the API, after its COMMIT), claims
// it and confirms it printed. No screen changes: there are no screenshots.
// flow: ninguno — FIX base
// What is made here is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql } from './helpers';
import { stamp } from './sale-helpers';

const RUN = stamp();
const PRINTER = `e2e WS label ${RUN}`;

interface Frame {
  type: string;
  [key: string]: unknown;
}

test.afterAll(() => {
  psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like 'e2e WS %')`);
  psql(`update printing_settings set label_printer_id = null where label_printer_id in (select id from printing_printer where name like 'e2e WS %')`);
  psql(`delete from printing_printer where name like 'e2e WS %'`);
});

/** Every frame the hub sent on the page's socket so far. */
async function frames(page: Page): Promise<Frame[]> {
  return page.evaluate(() => (window as unknown as { printFrames: Frame[] }).printFrames);
}

async function sendFrame(page: Page, frame: Frame): Promise<void> {
  await page.evaluate((f) => (window as unknown as { printSocket: WebSocket }).printSocket.send(JSON.stringify(f)), frame);
}

test('ninguno — FIX base: the device opens /ws/print, is woken by a new job, takes it and confirms it', async ({ page, context }) => {
  await login(page, A, '/printing/printers');
  // A label printer: no app queues labels on its own, so the oldest waiting job of its role is this spec's.
  const printer = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
    name: PRINTER,
    kind: 'network',
    address: '10.0.0.88',
    usage: 'label',
  });
  expect(printer.status).toBe(201);

  await page.evaluate(
    (printerId) =>
      new Promise<void>((resolve, reject) => {
        const socket = new WebSocket(`${location.origin.replace(/^http/, 'ws')}/ws/print`);
        const page = window as unknown as { printSocket: WebSocket; printFrames: unknown[] };
        page.printSocket = socket;
        page.printFrames = [];
        socket.onmessage = (event) => page.printFrames.push(JSON.parse(String(event.data)));
        socket.onopen = () => {
          socket.send(JSON.stringify({ type: 'hello', session: '', deviceId: 'e2e-ws-till', printers: [printerId] }));
          resolve();
        };
        socket.onerror = () => reject(new Error('the print channel did not open'));
      }),
    printer.data.id,
  );
  await expect.poll(() => frames(page)).toContainEqual({
    type: 'ready',
    deviceId: 'e2e-ws-till',
    roles: ['label'],
    heartbeatSeconds: 30,
  });

  const queued = await api<{ job: { id: string } }>(context, A, 'POST', '/printing/jobs', {
    document_type: 'barcode_label',
    document: { product_name: 'Shampoo', barcode: '8412345678905', price: 9.5 },
    printer: printer.data.id,
    job_key: `e2e-ws-${RUN}`,
    source_ref: `e2e-WS-${RUN}`,
  });
  expect(queued.status).toBe(201);
  const jobId = queued.data.job.id;

  // The nudge, after the COMMIT: never the document.
  await expect.poll(() => frames(page)).toContainEqual({ type: 'wake', role: 'label' });

  await sendFrame(page, { type: 'claim', role: 'label' });
  await expect
    .poll(async () => (await frames(page)).find((f) => f.type === 'job'))
    .toMatchObject({
      type: 'job',
      jobId,
      role: 'label',
      documentType: 'barcode_label',
      document: { product_name: 'Shampoo', barcode: '8412345678905' },
      attempts: 1,
      target: 'network:10.0.0.88:9100',
    });

  await sendFrame(page, { type: 'done', jobId });
  await expect.poll(() => frames(page)).toContainEqual({ type: 'ack', jobId, confirmed: true });
  const listed = await api<{ rows: { id: string; status: string }[] }>(
    context,
    A,
    'GET',
    `/printing/jobs?search=${encodeURIComponent(`e2e-WS-${RUN}`)}`,
  );
  expect(listed.data.rows.find((row) => row.id === jobId)?.status).toBe('done');
  expect((await frames(page)).filter((f) => f.type === 'error')).toEqual([]);
});

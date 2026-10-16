// Printing → Queue and Settings in Chrome (PRINTING-F01, F06, F14, F18; apps/printing/WORKBOOK.md): a job the
// device could not print fails after five hand-outs (the device's side by the API: claim and fail), the owner
// sends it back to the queue and then cancels it with a reason; the owner sets the ticket settings and the
// kitchen's printer, and the employee reads them blocked. Screenshots of both pages in the three viewports.
// What is made here is deleted, and the settings put back, after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shown } from './helpers';
import { dialog, fill, pick } from './inventory-helpers';
import { shots, stamp } from './sale-helpers';

const RUN = stamp();
const KITCHEN = `e2e Kitchen ${RUN}`;
const REF = `e2e-T-${RUN}`;
let before: Record<string, unknown> | undefined;

interface Job {
  id: string;
  status: string;
  attempts: number;
  cancelled_by: string;
  cancel_reason: string;
}

test.afterAll(() => {
  psql(`delete from printing_printjob where reference like 'e2e%' or printer_id in (select id from printing_printer where name like 'e2e %')`);
  if (before && before.updated_at === null) psql('delete from printing_settings');
  else if (before) {
    psql(
      `update printing_settings set open_drawer_on_sale = ${before.open_drawer_on_sale ? 'true' : 'false'}, ` +
        `kitchen_printer_id = ${before.kitchen_printer_id ? `'${String(before.kitchen_printer_id)}'` : 'null'}`,
    );
  }
  for (const column of ['receipt_printer_id', 'kitchen_printer_id', 'bar_printer_id', 'label_printer_id']) {
    psql(`update printing_settings set ${column} = null where ${column} in (select id from printing_printer where name like 'e2e %')`);
  }
  psql(`delete from printing_printer where name like 'e2e %'`);
});

async function jobsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-jobs-row], [data-testid=printing-jobs-empty]').first().waitFor({ state: 'visible' });
}

async function settingsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-settings-heading]').waitFor({ state: 'visible' });
}

async function jobByRef(context: BrowserContext): Promise<Job> {
  const listed = await api<{ rows: Job[] }>(context, A, 'GET', `/printing/jobs?search=${encodeURIComponent(REF)}`);
  return listed.data.rows[0];
}

async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const hook = `printing-jobs-row-${id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=printing-jobs-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

test('PRINTING-F18, F14: a job that fails five times is sent back, then cancelled with its reason', async ({ page, context }) => {
  await login(page, A, '/printing/jobs');
  const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
    name: KITCHEN,
    kind: 'network',
    address: '10.0.0.77',
    usage: 'kitchen',
  });
  expect(created.status).toBe(201);
  const queued = await api<{ job: { id: string } }>(context, A, 'POST', '/printing/jobs', {
    document_type: 'kitchen_order',
    document: { order_number: 7, table: '4', items: [{ name: 'Paella', quantity: 2 }] },
    source_ref: REF,
    job_key: `e2e-${RUN}`,
  });
  expect(queued.status).toBe(201);
  // The device's side (base's /ws/print, by the API): five hand-outs, five failures.
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const claim = await api<{ job: { id: string } | null }>(context, A, 'POST', '/printing/jobs/claim', {
      printers: [created.data.id],
      device: 'e2e device',
    });
    expect(claim.data.job?.id).toBe(queued.data.job.id);
    await api(context, A, 'POST', '/printing/jobs/fail', {
      job_id: queued.data.job.id,
      error: 'printer unreachable',
      device: 'e2e device',
      attempt,
    });
  }
  expect((await jobByRef(context)).status).toBe('failed');

  await jobsReady(page);
  const row = shown(page).locator('[data-testid=printing-jobs-row]').filter({ hasText: REF });
  await expect(row).toContainText(/Failed|Fallido/);
  await expect(row).toContainText('printer unreachable');
  await shots(page, 'printing-queue', jobsReady);

  await rowAction(page, queued.data.job.id, 'retry');
  await expect.poll(async () => (await jobByRef(context)).status).toBe('pending');
  await expect(row).toContainText(/Pending|Pendiente/);

  await rowAction(page, queued.data.job.id, 'cancel');
  const modal = dialog(page, 'printing-cancel-job');
  await expect(modal).toBeVisible();
  await fill(modal, 'printing-cancel-job-reason', 'e2e reason');
  await modal.locator('[data-testid=printing-cancel-job-submit]').click();
  await expect(modal).toBeHidden();
  await expect.poll(async () => (await jobByRef(context)).status).toBe('cancelled');
  expect((await jobByRef(context)).cancel_reason).toBe('e2e reason');
  await expect(row).toContainText(/Cancelled by|Cancelado por/);
});

test('PRINTING-F06: the owner opens the drawer at checkout and chooses the kitchen’s printer', async ({ page, context }) => {
  await login(page, A, '/printing/settings');
  before = (await api<Record<string, unknown>>(context, A, 'GET', '/printing/settings')).data;
  await settingsReady(page);
  await shots(page, 'printing-settings', settingsReady);
  await shown(page).locator('[data-testid=printing-setting-open_drawer_on_sale]').click();
  await pick(page, shown(page).locator('[data-testid=printing-setting-kitchen_printer]'), KITCHEN);
  const save = shown(page).locator('[data-testid=printing-settings-save]');
  await expect(save).not.toHaveAttribute('aria-disabled', 'true');
  await save.click();
  await expect
    .poll(async () => (await api<{ open_drawer_on_sale: boolean; kitchen_printer_id: string | null }>(context, A, 'GET', '/printing/settings')).data)
    .toMatchObject({ open_drawer_on_sale: !before?.open_drawer_on_sale });
  const kitchen = await api<{ rows: { id: string; name: string }[] }>(context, A, 'GET', `/printing/printers?search=${encodeURIComponent(KITCHEN)}`);
  expect((await api<{ kitchen_printer_id: string | null }>(context, A, 'GET', '/printing/settings')).data.kitchen_printer_id).toBe(kitchen.data.rows[0].id);
});

test('PRINTING-F06: the employee reads the settings blocked', async ({ page }) => {
  await login(page, A, '/printing/settings', EMPLOYEE);
  await settingsReady(page);
  await expect(shown(page).locator('[data-testid=printing-settings-read-only]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=printing-settings-save]')).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=printing-setting-open_drawer_on_sale]')).toBeDisabled();
});

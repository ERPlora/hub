// Printing → Printers in Chrome (PRINTING-F01, F03, F04, F05, F19; apps/printing/WORKBOOK.md): the owner adds
// a network printer through its window, sends it a test page (it waits in the queue, and the summary says so),
// changes its role and deactivates it; the employee sees the printers and tests, without adding or editing.
// Screenshots of the page in the three viewports. The printers and jobs made here are deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shown } from './helpers';
import { dialog, fill, pick } from './inventory-helpers';
import { shots, stamp } from './sale-helpers';

const RUN = stamp();
const TILL = `e2e Till ${RUN}`;

interface Printer {
  id: string;
  name: string;
  usage: string;
  is_active: boolean;
  target: string;
}

test.afterAll(() => {
  psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like 'e2e %')`);
  // Only the defaults that point at this spec's printers: the hub's own choices stay as they were.
  for (const column of ['receipt_printer_id', 'kitchen_printer_id', 'bar_printer_id', 'label_printer_id']) {
    psql(`update printing_settings set ${column} = null where ${column} in (select id from printing_printer where name like 'e2e %')`);
  }
  psql(`delete from printing_printer where name like 'e2e %'`);
});

async function printersReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-printers-row], [data-testid=printing-printers-empty]').first().waitFor({ state: 'visible' });
}

/** Runs a row action of the printers list: its inline button, or the row's «⋮» menu when it folded there. */
async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const hook = `printing-printers-row-${id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=printing-printers-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

async function byName(context: import('@playwright/test').BrowserContext, name: string): Promise<Printer> {
  const listed = await api<{ rows: Printer[] }>(context, A, 'GET', `/printing/printers?search=${encodeURIComponent(name)}`);
  return listed.data.rows.find((p) => p.name === name)!;
}

test('PRINTING-F03, F05: the owner adds a network printer and sends it a test page', async ({ page, context }) => {
  await login(page, A, '/printing/printers');
  await printersReady(page);
  await expect(shown(page).locator('[data-testid=printing-printers-intro]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=printing-summary-heading]')).toBeVisible();
  await shown(page).locator('[data-testid=printing-printers-add]').click();
  const modal = dialog(page, 'printing-printer');
  await expect(modal).toBeVisible();
  await fill(modal, 'printing-printer-name', TILL);
  await fill(modal, 'printing-printer-address', '192.168.1.50');
  await modal.locator('[data-testid=printing-printer-submit]').click();
  await expect(modal).toBeHidden();
  const row = shown(page).locator('[data-testid=printing-printers-row]').filter({ hasText: TILL });
  await expect(row).toContainText('192.168.1.50:9100');
  const till = await byName(context, TILL);
  expect(till.target).toBe('network:192.168.1.50:9100');

  await rowAction(page, till.id, 'test');
  await expect.poll(async () => (await api<{ total: number }>(context, A, 'GET', `/printing/jobs?printer_id=${till.id}`)).data.total).toBe(1);
  // The summary is live: the receipt role now has a job waiting on its printer.
  await expect(shown(page).locator('[data-testid=printing-summary-card-receipt]')).toContainText(/Waiting: \d+|En cola: \d+/);
  await shots(page, 'printing-printers', printersReady);
});

test('PRINTING-F04: the owner gives the printer another role and deactivates it', async ({ page, context }) => {
  await login(page, A, '/printing/printers');
  const till = await byName(context, TILL);
  await printersReady(page);
  await rowAction(page, till.id, 'edit');
  const modal = dialog(page, 'printing-printer');
  await expect(modal).toBeVisible();
  await pick(page, modal.locator('[data-testid=printing-printer-usage]'), /Kitchen|Cocina/);
  await modal.locator('[data-testid=printing-printer-submit]').click();
  await expect(modal).toBeHidden();
  await expect.poll(async () => (await byName(context, TILL)).usage).toBe('kitchen');
  await rowAction(page, till.id, 'toggle');
  await expect.poll(async () => (await byName(context, TILL)).is_active).toBe(false);
  await expect(shown(page).locator(`[data-testid=printing-printers-state-${till.id}]`).first()).toContainText(/Inactive|Inactiva/);
  await rowAction(page, till.id, 'toggle');
  await expect.poll(async () => (await byName(context, TILL)).is_active).toBe(true);
});

test('PRINTING-F03: the employee sees the printers without adding or editing', async ({ page, context }) => {
  await login(page, A, '/printing/printers', EMPLOYEE);
  const till = await byName(context, TILL);
  await printersReady(page);
  await expect(shown(page).locator('[data-testid=printing-printers-add]')).toHaveCount(0);
  await expect(shown(page).locator(`[data-testid=printing-printers-row-${till.id}-edit]`)).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=printing-printers-row]').filter({ hasText: TILL })).toBeVisible();
});

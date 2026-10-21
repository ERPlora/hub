// Printing → Printers in Chrome (PRINTING-F01, F02, F03, F04, F05, F19; apps/printing/WORKBOOK.md): the owner
// adds a network printer through its window, sends it a test page (it waits in the queue, and the summary says
// so and names the printer each role prints on), the device fails it (the printer shows «With errors» and its
// last error), the owner changes its role and deactivates it; «Search printers» says a browser cannot look,
// and inside the app (its bridge answered by the test: no network scan here) opens «New printer» filled in with
// what the device found; the employee sees the printers and tests, without adding or editing. Screenshots of
// every flow in the three viewports. The printers and jobs made here are deleted after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shown } from './helpers';
import { dialog, fill, pick } from './inventory-helpers';
import { claim, fail, flowShots, forgetDevices } from './printing-helpers';
import { shots, stamp } from './sale-helpers';

// One printer goes through every test, in order: a failure stops the rest instead of a new worker's names.
test.describe.configure({ mode: 'serial' });

const RUN = stamp();
const TILL = `e2e Till ${RUN}`;
const FOUND = `e2e Found ${RUN}`;
const FOUND_ADDRESS = '192.168.77.21';
/** The device the API plays (PRINTING-F18): the owner's first claim from it sets it up. */
const DEVICE = `e2e printers device ${RUN}`;

interface Printer {
  id: string;
  name: string;
  usage: string;
  is_active: boolean;
  target: string;
  last_error: string;
}

interface Usage {
  usage: string;
  prints_on: string | null;
}

test.afterAll(() => {
  psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like 'e2e %')`);
  // Only the defaults that point at this spec's printers: the hub's own choices stay as they were.
  for (const column of ['receipt_printer_id', 'kitchen_printer_id', 'bar_printer_id', 'label_printer_id']) {
    psql(`update printing_settings set ${column} = null where ${column} in (select id from printing_printer where name like 'e2e %')`);
  }
  forgetDevices('e2e %', { ids: [DEVICE] });
  psql(`delete from printing_printer where name like 'e2e %'`);
});

async function printersReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-printers-row], [data-testid=printing-printers-empty]').first().waitFor({ state: 'visible' });
}

async function jobsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-jobs-row], [data-testid=printing-jobs-empty]').first().waitFor({ state: 'visible' });
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

async function byName(context: BrowserContext, name: string): Promise<Printer> {
  const listed = await api<{ rows: Printer[] }>(context, A, 'GET', `/printing/printers?search=${encodeURIComponent(name)}`);
  return listed.data.rows.find((p) => p.name === name)!;
}

async function printsOn(context: BrowserContext, usage: string): Promise<string | null> {
  const summary = await api<{ usages: Usage[] }>(context, A, 'GET', '/printing/jobs/summary');
  expect(summary.status, JSON.stringify(summary.data)).toBe(200);
  return summary.data.usages.find((u) => u.usage === usage)?.prints_on ?? null;
}

test('PRINTING-F03, F05, F01: the owner adds a network printer and sends it a test page', async ({ page, context }) => {
  await login(page, A, '/printing/printers');
  await printersReady(page);
  await expect(shown(page).locator('[data-testid=printing-printers-intro]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=printing-summary-heading]')).toBeVisible();
  // In a browser the note speaks of the browser (printing#37): it cannot reach a printer by itself.
  await expect(shown(page).locator('[data-testid=printing-printers-app-note]')).toContainText(/browser|navegador/);
  await shown(page).locator('[data-testid=printing-printers-add]').click();
  const modal = dialog(page, 'printing-printer');
  await expect(modal).toBeVisible();
  await fill(modal, 'printing-printer-name', TILL);
  await fill(modal, 'printing-printer-address', '192.168.1.50');
  await flowShots(page, 'PRINTING-F03', async () => {
    await expect(modal.locator('[data-testid=printing-printer-submit]')).toBeVisible();
  });
  await modal.locator('[data-testid=printing-printer-submit]').click();
  await expect(modal).toBeHidden();
  const row = shown(page).locator('[data-testid=printing-printers-row]').filter({ hasText: TILL });
  await expect(row).toContainText('192.168.1.50:9100');
  const till = await byName(context, TILL);
  expect(till.target).toBe('network:192.168.1.50:9100');

  await rowAction(page, till.id, 'test');
  await expect.poll(async () => (await api<{ total: number }>(context, A, 'GET', `/printing/jobs?printer_id=${till.id}`)).data.total).toBe(1);
  // The summary is live: the receipt role now has a job waiting, and its card names the printer it prints
  // on (hub#1527) — the one the server says, the default or else the first active receipt printer.
  const receipt = shown(page).locator('[data-testid=printing-summary-card-receipt]');
  await expect(receipt).toContainText(/Waiting: \d+|En cola: \d+/);
  const on = await printsOn(context, 'receipt');
  expect(on).not.toBeNull();
  await expect(shown(page).locator('[data-testid=printing-summary-prints-on-receipt]')).toHaveText(new RegExp(`(Prints on|Imprime en): ${on!.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\.`));
  await shots(page, 'printing-printers', printersReady);
  await flowShots(page, 'PRINTING-F01', async (p) => {
    await expect(shown(p).locator('[data-testid=printing-summary-prints-on-receipt]')).toBeVisible();
  });

  // The test page is a job of the queue like any other: «Test page», on this printer.
  await login(page, A, '/printing/jobs');
  await jobsReady(page);
  const sheet = shown(page).locator('[data-testid=printing-jobs-row]').filter({ hasText: /Test page|Hoja de prueba/ }).filter({ hasText: TILL });
  await expect(sheet).toHaveCount(1);
  await expect(sheet).toContainText(/Pending|Pendiente/);
  await flowShots(page, 'PRINTING-F05', async (p) => {
    await expect(shown(p).locator('[data-testid=printing-jobs-row]').filter({ hasText: TILL }).first()).toBeVisible();
  });
});

test('PRINTING-F19: a printer whose job did not come out says so, with its last error', async ({ page, context }) => {
  await login(page, A, '/printing/printers');
  const till = await byName(context, TILL);
  // The device's side (base's /ws/print, by the API): it takes the test page and says it did not print.
  const job = await claim(context, till.id, DEVICE);
  expect(job).not.toBeNull();
  await fail(context, job!, 'paper out', DEVICE);
  expect((await byName(context, TILL)).last_error).toBe('paper out');

  await printersReady(page);
  const state = shown(page).locator(`[data-testid=printing-printers-state-${till.id}]`).first();
  await expect(state).toContainText(/With errors|Con errores/);
  await expect(state).toContainText(/Last error: paper out|Último error: paper out/);
  await flowShots(page, 'PRINTING-F19', async (p) => {
    await expect(shown(p).locator(`[data-testid=printing-printers-state-${till.id}]`).first()).toBeVisible();
  });
});

test('PRINTING-F04: the owner gives the printer another role and deactivates it', async ({ page, context }) => {
  await login(page, A, '/printing/printers');
  const till = await byName(context, TILL);
  await printersReady(page);
  await rowAction(page, till.id, 'edit');
  const modal = dialog(page, 'printing-printer');
  await expect(modal).toBeVisible();
  await pick(page, modal.locator('[data-testid=printing-printer-usage]'), /Kitchen|Cocina/);
  await flowShots(page, 'PRINTING-F04', async () => {
    await expect(modal.locator('[data-testid=printing-printer-usage]')).toBeVisible();
  });
  await modal.locator('[data-testid=printing-printer-submit]').click();
  await expect(modal).toBeHidden();
  await expect.poll(async () => (await byName(context, TILL)).usage).toBe('kitchen');
  await rowAction(page, till.id, 'toggle');
  await expect.poll(async () => (await byName(context, TILL)).is_active).toBe(false);
  await expect(shown(page).locator(`[data-testid=printing-printers-state-${till.id}]`).first()).toContainText(/Inactive|Inactiva/);
  await rowAction(page, till.id, 'toggle');
  await expect.poll(async () => (await byName(context, TILL)).is_active).toBe(true);
});

test('PRINTING-F02: in a browser «Search printers» says it cannot look, and adding by address stays', async ({ page }) => {
  await login(page, A, '/printing/printers');
  await printersReady(page);
  await shown(page).locator('[data-testid=printing-printers-discover]').click();
  const modal = dialog(page, 'printing-discover');
  await expect(modal.locator('[data-testid=printing-discover-browser]')).toBeVisible();
  await expect(modal.locator('[data-testid=printing-discover-again]')).toHaveCount(0);
  await modal.locator('[data-testid=printing-discover-submit]').click();
  const form = dialog(page, 'printing-printer');
  await expect(form).toBeVisible();
  await expect(form.locator('[data-testid=printing-printer-name] input')).toHaveValue('');
});

test('PRINTING-F02: inside the app «Search printers» lists what the device found and adds it filled in', async ({ page, context }) => {
  // The app's bridge (ERPlora/app `erplora_discover_printers`), answered here: one receipt printer on the
  // network and one office printer (IPP, no ESC/POS) that cannot be added. Any other command is refused.
  await context.addInitScript(
    ({ name, address }) => {
      const invoke = (command: string) =>
        command === 'erplora_discover_printers'
          ? Promise.resolve({
              status: 'scanned',
              printers: [
                { id: `network:${address}:9100`, name, type: 'network', paper_width: 80 },
                { id: 'network:192.168.77.40:631', name: 'Office laser', type: 'network', category: 'a4' },
              ],
            })
          : Promise.reject('unknown_command');
      (window as unknown as { __TAURI__: unknown }).__TAURI__ = { core: { invoke } };
    },
    { name: FOUND, address: FOUND_ADDRESS },
  );
  await login(page, A, '/printing/printers');
  await printersReady(page);
  // Inside the app nobody is told about a browser (printing#37).
  await expect(shown(page).locator('[data-testid=printing-printers-app-note]')).not.toContainText(/browser|navegador/);
  await shown(page).locator('[data-testid=printing-printers-discover]').click();
  const modal = dialog(page, 'printing-discover');
  await expect(modal.locator('[data-testid=printing-discover-row]')).toHaveCount(1);
  await expect(modal.locator('[data-testid=printing-discover-row]')).toContainText(FOUND);
  await expect(modal.locator('[data-testid=printing-discover-row]')).toContainText(`${FOUND_ADDRESS}:9100`);
  await flowShots(page, 'PRINTING-F02', async () => {
    await expect(modal.locator('[data-testid=printing-discover-row-0-add]')).toBeVisible();
  });
  await modal.locator('[data-testid=printing-discover-row-0-add]').click();
  const form = dialog(page, 'printing-printer');
  await expect(form).toBeVisible();
  await expect(form.locator('[data-testid=printing-printer-name] input')).toHaveValue(FOUND);
  await expect(form.locator('[data-testid=printing-printer-address] input')).toHaveValue(FOUND_ADDRESS);
  await form.locator('[data-testid=printing-printer-submit]').click();
  await expect(form).toBeHidden();
  await expect.poll(async () => (await byName(context, FOUND))?.target).toBe(`network:${FOUND_ADDRESS}:9100`);

  // Searching again: the business already has it.
  await shown(page).locator('[data-testid=printing-printers-discover]').click();
  await expect(modal.locator('[data-testid=printing-discover-row-0-added]')).toBeVisible();
  await expect(modal.locator('[data-testid=printing-discover-row-0-add]')).toHaveCount(0);
});

test('PRINTING-F03: the employee sees the printers without adding or editing', async ({ page, context }) => {
  await login(page, A, '/printing/printers', EMPLOYEE);
  const till = await byName(context, TILL);
  await printersReady(page);
  await expect(shown(page).locator('[data-testid=printing-printers-add]')).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=printing-printers-discover]')).toHaveCount(0);
  await expect(shown(page).locator(`[data-testid=printing-printers-row-${till.id}-edit]`)).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=printing-printers-row]').filter({ hasText: TILL })).toBeVisible();
});

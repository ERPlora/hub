// VeriFactu flow by flow (APP-VERIFACTU; apps/verifactu/WORKBOOK.md), in Chrome against the real Hub, Invoicing and
// Sales, no mocks. Each flow with a screen leaves its evidence in the three sizes of the migration
// (`APP-VERIFACTU-<flow>-390|834|1440` in `.artifacts`):
//   - VERIFACTU-F01: «My apps» opens VeriFactu on Records, with its six tabs;
//   - VERIFACTU-F16, F18: Records lists the run's record, found by its invoice, with «Verify at the AEAT»;
//   - VERIFACTU-F17, F25, F35: its record says why it waits; «Send now» and «Ask the AEAT» say why nothing reached
//     the AEAT (this server has no gateway), and the record stays in the queue;
//   - VERIFACTU-F24: a record the AEAT rejected says so and what to do, and «Correct» seals a new record; Records says
//     by each rejection «Corrected» (a link to the new record) or «Pending correction» and filters the ones left;
//   - VERIFACTU-F30: «Cancel record» asks why before sealing the cancellation;
//   - VERIFACTU-F20, F21, F22: the queue lists what is not in the AEAT; «Process queue» and «Retry» answer;
//   - VERIFACTU-F31: Events tells what happened, the latest first;
//   - VERIFACTU-F26–F29: Recovery validates the chain, asks the AEAT and offers both recoveries, asking first;
//   - VERIFACTU-F27: «Latest records at the AEAT» searches the last photo on the server;
//   - VERIFACTU-F09–F12: Settings, two columns on a desk as the old screen: back to testing, the connection test,
//     the test invoice and the responsible declaration.
// The gateway is not configured on this server, as in the other VeriFactu specs: what would go to the AEAT says why
// it could not, and nothing is ever taken as accepted. The AEAT's rejection (F24) and a business already in production
// (F09) are set on the run's own rows in the database, as the AEAT's answer and going live would leave them; the logic
// behind them is the Python suite's (`apps/verifactu/tests`). What the run makes is removed after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, openApps, psql, shot, shown } from './helpers';
import { cleanInvoices, ensureIssuer, FLOW_VIEWPORTS, issuedIds, snapshotSeries } from './invoice-helpers';
import { stamp } from './sale-helpers';

const RUN = stamp();
const STARTED = new Date().toISOString();
/** VeriFactu's configuration before the run (the columns F09 moves), or `null` when the run made it. */
let configBefore: { environment: string; production_since: string } | null = null;

interface RecordOut {
  id: string;
  invoice_number: string;
  status: string;
}

/** The page in the three sizes, as `APP-VERIFACTU-<flow>-<size>`, each once `ready` says it painted. */
async function flowShots(page: Page, flow: string, ready: (page: Page) => Promise<void>): Promise<void> {
  const restore = page.viewportSize() ?? { width: 1280, height: 860 };
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await page.screenshot({ path: shot(`APP-VERIFACTU-${flow}-${viewport.label}`) });
  }
  await page.setViewportSize(restore);
}

/** `target` scrolled into view (the evidence shows what the flow is about, not the top of a long page), and shown. */
async function seen(target: Locator): Promise<void> {
  // A live list paints its rows again when a result arrives: scroll whatever row is there by then.
  await expect(async () => {
    await target.scrollIntoViewIfNeeded({ timeout: 2000 });
  }).toPass();
  await expect(target).toBeVisible();
}

/** A ticket issued through Invoicing's API, sealed in its emission (setup; the checks are VeriFactu's). */
async function ticket(context: BrowserContext): Promise<RecordOut> {
  const res = await api<{ id: string; number: string; verifactu_status: string | null }>(context, A, 'POST', '/invoice/invoices', {
    series_code: 'TICKET',
    lines: [{ description: `e2e VeriFactu flows ${RUN}`, quantity: '1', unit_price: 1000, tax_rate: '21' }],
  });
  expect(res.status, 'Invoicing issues the ticket').toBe(201);
  expect(res.data.verifactu_status, 'its record is sealed in the same commit').toBe('sealed');
  issuedIds.add(res.data.id);
  const id = psql(`select id from verifactu_record where invoice_id = '${res.data.id}' and record_type = 'alta'`);
  return { id, invoice_number: res.data.number, status: 'pending' };
}

/** The confirmation card titled `title` (Ionic keeps other dialogs in the page: the apps launcher is one too). */
const confirmation = (page: Page, title: string): Locator => page.locator('ion-modal:not(.overlay-hidden)', { hasText: title });

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/verifactu/records');
  snapshotSeries();
  await ensureIssuer(context);
  const row = psql("select environment || '|' || coalesce(production_since::text, '') from verifactu_config");
  configBefore = row ? { environment: row.split('|')[0], production_since: row.split('|')[1] } : null;
  await context.close();
});

test.afterAll(() => {
  try {
    psql(
      [
        `delete from verifactu_event where created_at >= '${STARTED}'`,
        `delete from verifactu_aeatrecord where invoice_number = 'E2E-AEAT-${RUN}'`,
        configBefore
          ? `update verifactu_config set environment = '${configBefore.environment}', production_since = ${configBefore.production_since ? `'${configBefore.production_since}'` : 'null'}`
          : 'select 1',
      ].join('; '),
    );
  } finally {
    // The records go with their invoices (a record keeps its invoice), and the chain heads point back at what is left.
    cleanInvoices();
  }
});

test('VERIFACTU-F01: «My apps» opens VeriFactu on Records, with its six tabs', async ({ page }) => {
  await login(page, A, '/');
  const apps = await openApps(page);
  await apps.locator('[data-testid=apps-launcher-app]', { hasText: 'VeriFactu' }).first().click();
  await expect(page).toHaveURL(/\/verifactu\/records$/);
  const tabs = shown(page).locator('ion-segment.tabbar ion-segment-button');
  await expect(tabs).toHaveCount(6);
  await expect(tabs).toHaveText(['Records', 'Contingency', 'Events', 'Recovery', 'Configuration', 'Settings']);
  await flowShots(page, 'F01', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-records-search]'));
  });
});

test('VERIFACTU-F16, F18: Records lists the record by its invoice, with «Verify at the AEAT»', async ({ page, context }) => {
  await login(page, A, '/verifactu/records');
  const record = await ticket(context);
  const list = shown(page);
  await list.locator('[data-testid=verifactu-records-search] input').fill(record.invoice_number);
  const row = list.locator('[data-testid=verifactu-records-row]').filter({ hasText: record.invoice_number });
  await expect(row).toHaveCount(1);
  await expect(row.locator('[data-testid=verifactu-records-status]')).toHaveText('Pending');
  await flowShots(page, 'F16', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-records-row]').filter({ hasText: record.invoice_number }).first());
  });
  // F18: the row's «Verify at the AEAT» is the QR's link to the AEAT's site (the test one, in testing).
  const verify = list.locator(`[data-testid=verifactu-records-row-${record.id}-verify]`);
  await expect(verify).toHaveCount(1);
  await flowShots(page, 'F18', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-records-row]').filter({ hasText: record.invoice_number }).first());
  });
});

test('VERIFACTU-F17, F25, F35: the record says why it waits; «Send now» and «Ask the AEAT» say why nothing reached the AEAT', async ({ page, context }) => {
  await login(page, A, '/verifactu/records');
  const record = await ticket(context);
  await page.goto(`${A}/verifactu/records/${record.id}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=verifactu-record-title]')).toHaveText(`Record ${record.invoice_number}`);
  await expect(detail.locator('[data-testid=verifactu-record-waiting]')).toContainText("ERPlora's sending gateway is not configured on this server");
  await flowShots(page, 'F17', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-record-waiting]'));
  });

  // F25: sent by hand, it is refused before anything leaves (no gateway): said above the buttons, still pending.
  await detail.locator('[data-testid=verifactu-record-transmit]').click();
  const error = detail.locator('[data-testid=verifactu-record-error]');
  await expect(error).toContainText("ERPlora's sending gateway is not configured on this server");
  await flowShots(page, 'F25', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-record-error]'));
  });

  // F35: asking the AEAT whether it already has it needs the gateway too; nothing leaves the queue.
  await detail.locator('[data-testid=verifactu-record-ask]').click();
  await expect(error).toContainText('gateway');
  await expect(detail.locator('[data-testid=verifactu-record-status]')).toContainText('Pending');
  expect(psql(`select status from verifactu_record where id = '${record.id}'`)).toBe('pending');
  await flowShots(page, 'F35', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-record-ask]'));
  });
});

test('VERIFACTU-F24: a rejected record says what to do and «Correct» seals a new record of the same invoice', async ({ page, context }) => {
  await login(page, A, '/verifactu/records');
  const record = await ticket(context);
  // The AEAT's answer, as the sending leaves it on a rejection (the real answers: the Python suite's fixtures).
  psql(
    `update verifactu_record set status = 'rejected', aeat_code = '1189', aeat_message = 'e2e: Falta Destinatarios' where id = '${record.id}'`,
  );
  await page.goto(`${A}/verifactu/records/${record.id}`);
  const detail = shown(page);
  const rejected = detail.locator('[data-testid=verifactu-record-rejected]');
  await expect(rejected).toContainText('The AEAT rejected it');
  await expect(rejected).toContainText('1189');
  await expect(detail.locator('[data-testid=verifactu-record-ask]')).toHaveCount(0);
  await flowShots(page, 'F24', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-record-rejected]'));
  });

  await detail.locator('[data-testid=verifactu-record-correct]').click();
  const dialog = confirmation(page, `Correct the record of ${record.invoice_number}?`);
  await expect(dialog).toBeVisible();
  await dialog.locator('ion-button', { hasText: 'Correct' }).click();
  await expect(page.locator('ion-toast').filter({ hasText: `Correction of ${record.invoice_number} sealed` })).toBeVisible();
  const rows = psql(`select status || ':' || correction from verifactu_record where invoice_number = '${record.invoice_number}' order by sequence`);
  expect(rows.split('\n')).toEqual(['rejected:false', 'pending:true']);
});

test('VERIFACTU-F24: Records says by each rejection «Corrected» (a link to the new record) or «Pending correction», and filters the ones left', async ({
  page,
  context,
}) => {
  await login(page, A, '/verifactu/records');
  const corrected = await ticket(context);
  const left = await ticket(context);
  // The AEAT's answer, as the sending leaves it on a rejection (the real answers: the Python suite's fixtures).
  psql(
    `update verifactu_record set status = 'rejected', aeat_code = '1189', aeat_message = 'e2e: Falta Destinatarios' where id in ('${corrected.id}', '${left.id}')`,
  );
  const sealed = await api<{ record: { id: string } }>(context, A, 'POST', '/verifactu/records/correct', { record_id: corrected.id });
  expect(sealed.status, 'the first rejection is corrected with a new record').toBeLessThan(300);
  const correction = sealed.data.record.id;

  await page.goto(`${A}/verifactu/records`);
  const list = shown(page);
  const rowsOf = (number: string) => list.locator('[data-testid=verifactu-records-row]').filter({ hasText: number });
  const rejectedOf = (number: string) =>
    rowsOf(number).filter({ has: page.locator('[data-testid=verifactu-records-status]', { hasText: 'Rejected' }) });
  const link = rejectedOf(corrected.invoice_number).locator('[data-testid=verifactu-correction-corrected]');
  const pending = rejectedOf(left.invoice_number).locator('[data-testid=verifactu-correction-pending]');
  // The list follows itself: the correction sealed by the API already shows, and its rejection says so.
  await expect(link).toHaveText('Corrected');
  await expect(link).toHaveAttribute('href', `/verifactu/records/${correction}`);
  await expect(pending).toHaveText('Pending correction');
  // The correction itself waits in the queue: nothing to correct, no mark.
  const queued = rowsOf(corrected.invoice_number).filter({ has: page.locator('[data-testid=verifactu-records-status]', { hasText: 'Pending' }) });
  await expect(queued).toHaveCount(1);
  await expect(queued.locator('[data-testid^=verifactu-correction-]')).toHaveCount(0);
  await flowShots(page, 'F24-records', async (p) => {
    const view = shown(p);
    const row = view.locator('[data-testid=verifactu-records-row]').filter({ hasText: corrected.invoice_number }).filter({ has: p.locator('[data-testid=verifactu-correction-corrected]') });
    await seen(row.locator('[data-testid=verifactu-correction-corrected]'));
    await expect(view.locator('[data-testid=verifactu-records-row]').filter({ hasText: left.invoice_number }).locator('[data-testid=verifactu-correction-pending]')).toBeVisible();
    // The status and its mark never touch: side by side with a gap (a card), or one under the other (a narrow cell).
    const status = await row.locator('[data-testid=verifactu-records-status]').boundingBox();
    const mark = await row.locator('[data-testid=verifactu-correction-corrected]').boundingBox();
    if (!status || !mark) throw new Error('the status and its mark are painted');
    const sameLine = status.y < mark.y + mark.height && mark.y < status.y + status.height;
    const gap = sameLine ? mark.x - (status.x + status.width) : mark.y - (status.y + status.height);
    expect(gap, `the status and «Corrected» apart (${sameLine ? 'side by side' : 'stacked'})`).toBeGreaterThanOrEqual(3);
  });

  // «Pending correction» behind the funnel leaves only the ones left to correct.
  await page.setViewportSize({ width: 1440, height: 900 });
  const panel = list.locator('[data-testid=verifactu-records-filters-panel]');
  await list.locator('[data-testid=verifactu-records-filters-toggle]').click();
  await expect(panel).toBeVisible();
  await panel.locator('[data-testid=verifactu-records-filter-correction_status]').click();
  const popover = page.locator('ion-popover.select-popover');
  await popover.locator('ion-radio').filter({ hasText: /^\s*Pending correction\s*$/ }).click();
  await expect(popover).toHaveCount(0);
  await panel.locator('[data-testid=verifactu-records-filters-apply]').click();
  await expect(panel).toBeHidden();
  await expect(list.locator('[data-testid=verifactu-records-filters-count]')).toHaveText('1');
  await expect(rejectedOf(left.invoice_number)).toHaveCount(1);
  await expect(rowsOf(corrected.invoice_number)).toHaveCount(0);
  await expect(list.locator('[data-testid=verifactu-records-row]').filter({ hasNotText: 'Pending correction' })).toHaveCount(0);
  await flowShots(page, 'F24-records-filter', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-records-row]').filter({ hasText: left.invoice_number }));
  });

  // The rejection's detail links to the record that corrects it; the link opens it (not the rejected row).
  await page.goto(`${A}/verifactu/records/${corrected.id}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=verifactu-record-status]')).toHaveText('Rejected');
  await expect(detail.locator('[data-testid=verifactu-record-correct]')).toHaveCount(0);
  await flowShots(page, 'F24-record-corrected', async (p) => {
    const head = shown(p);
    await seen(head.locator('[data-testid=verifactu-correction-corrected]'));
    // «Corrected» beside its status sits on its line (never a few pixels below it), or under it when the head has no room.
    const status = await head.locator('[data-testid=verifactu-record-status]').boundingBox();
    // The pill itself, not its link's box: a link taller than its pill once let the pill sit below the status.
    const mark = await head.locator('[data-testid=verifactu-correction-corrected] .status-pill').boundingBox();
    if (!status || !mark) throw new Error('the status and «Corrected» are painted');
    const boxes = JSON.stringify({ status, mark });
    if (mark.y < status.y + status.height) {
      expect(Math.abs(status.y + status.height / 2 - (mark.y + mark.height / 2)), `«Corrected» on its status's line: ${boxes}`).toBeLessThanOrEqual(1);
    } else {
      expect(mark.x, `«Corrected» wraps to the start of the next line: ${boxes}`).toBeLessThan(status.x);
    }
  });
  await detail.locator('[data-testid=verifactu-correction-corrected]').click();
  await expect(page).toHaveURL(new RegExp(`/verifactu/records/${correction}$`));
  await expect(shown(page).locator('[data-testid=verifactu-record-status]')).toHaveText('Pending');

  // From the list, too: the link goes to the new record, never to the rejected one its row opens.
  await page.goto(`${A}/verifactu/records`);
  await shown(page).locator('[data-testid=verifactu-records-search] input').fill(corrected.invoice_number);
  await rejectedOf(corrected.invoice_number).locator('[data-testid=verifactu-correction-corrected]').click();
  await expect(page).toHaveURL(new RegExp(`/verifactu/records/${correction}$`));
});

test('VERIFACTU-F30: «Cancel record» asks why before sealing the cancellation', async ({ page, context }) => {
  await login(page, A, '/verifactu/records');
  const record = await ticket(context);
  await page.goto(`${A}/verifactu/records/${record.id}`);
  await shown(page).locator('[data-testid=verifactu-record-cancel]').click();
  const dialog = page.locator('ion-modal[data-testid=verifactu-cancel]:not(.overlay-hidden)');
  await expect(dialog).toBeVisible();
  await flowShots(page, 'F30', async () => {
    await seen(dialog.locator('[data-testid=verifactu-cancel-reason]'));
  });
  await dialog.locator('[data-testid=verifactu-cancel-reason] textarea').fill('e2e duplicated ticket');
  await dialog.locator('[data-testid=verifactu-cancel-submit]').click();
  await expect(page.locator('ion-toast').filter({ hasText: `Cancellation of ${record.invoice_number} sealed` })).toBeVisible();
});

test('VERIFACTU-F20, F21, F22: the queue lists what is not in the AEAT; «Process queue» and «Retry» answer', async ({ page, context }) => {
  await login(page, A, '/verifactu/contingency');
  const record = await ticket(context);
  const queue = shown(page);
  await queue.locator('[data-testid=verifactu-queue-search] input').fill(record.invoice_number);
  const row = queue.locator('[data-testid=verifactu-queue-row]').filter({ hasText: record.invoice_number });
  await expect(row).toHaveCount(1);
  await flowShots(page, 'F20', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-queue-row]').filter({ hasText: record.invoice_number }).first());
  });

  await queue.locator('[data-testid=verifactu-queue-process]').click();
  await expect(queue.locator('[data-testid=verifactu-queue-result]')).toHaveText("ERPlora's sending gateway is not configured on this server");
  await flowShots(page, 'F21', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-queue-result]'));
  });

  await queue.locator(`[data-testid=verifactu-queue-row-${record.id}-retry]`).first().click();
  await expect(page.locator('ion-toast').filter({ hasText: `${record.invoice_number} goes out with the next pass.` })).toBeVisible();
  await flowShots(page, 'F22', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-queue-row]').filter({ hasText: record.invoice_number }).first());
  });
});

test('VERIFACTU-F31: Events tells what happened, the latest first', async ({ page, context }) => {
  await login(page, A, '/verifactu/events');
  const record = await ticket(context);
  const events = shown(page);
  await events.locator('[data-testid=verifactu-events-search] input').fill(record.invoice_number);
  await expect(events.locator('[data-testid=verifactu-events-row]').first()).toContainText(record.invoice_number);
  await flowShots(page, 'F31', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-events-row]').first());
  });
});

test('VERIFACTU-F26–F29: Recovery validates the chain, asks the AEAT and asks before either recovery', async ({ page, context }) => {
  await login(page, A, '/verifactu/recovery');
  await ticket(context);
  const view = shown(page);
  await expect(view.locator('[data-testid=verifactu-recovery-nif] input')).toHaveValue('B12345674');

  // F26: the chain of the run's issuer is intact.
  await view.locator('[data-testid=verifactu-recovery-validate]').click();
  await expect(view.locator('[data-testid=verifactu-recovery-integrity]')).toContainText('Fingerprint chain intact ✓');
  await flowShots(page, 'F26', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-recovery-integrity]'));
  });

  // F27: asking the AEAT needs the gateway: said, and the last photo stays as it was.
  await view.locator('[data-testid=verifactu-recovery-query]').click();
  await expect(view.locator('[data-testid=verifactu-recovery-result]')).toContainText('gateway');
  await flowShots(page, 'F27', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-recovery-result]'));
  });

  // F28: recovering from the AEAT asks first; cancelled, nothing happens.
  await view.locator('[data-testid=verifactu-recovery-recover]').click();
  const fromAeat = confirmation(page, 'Recover the chain from the AEAT');
  await expect(fromAeat).toBeVisible();
  await flowShots(page, 'F28', async () => {
    await seen(fromAeat.locator('ion-button', { hasText: 'Confirm recovery' }));
  });
  await fromAeat.locator('ion-button', { hasText: 'Cancel' }).click();
  await expect(fromAeat).toBeHidden();

  // F29: continuing from another application's fingerprint asks first; with records waiting to go out it is refused.
  await view.locator('[data-testid=verifactu-recovery-hash] input').fill('A'.repeat(64));
  await view.locator('[data-testid=verifactu-recovery-invoice] input').fill('OLD-2026-000099');
  await view.locator('[data-testid=verifactu-recovery-date] input').fill('2026-10-01');
  await view.locator('[data-testid=verifactu-recovery-manual]').click();
  const manual = confirmation(page, 'Continue the chain from an external fingerprint');
  await expect(manual).toBeVisible();
  await manual.locator('ion-button', { hasText: 'Confirm recovery' }).click();
  await expect(manual).toBeHidden();
  await expect(view.locator('[data-testid=verifactu-recovery-result]')).not.toHaveText('Operation completed.');
  await flowShots(page, 'F29', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-recovery-manual]'));
  });
});

test('VERIFACTU-F27: «Latest records at the AEAT» searches the last photo on the server and says when nothing matches', async ({ page }) => {
  // The photo as a «Query AEAT» leaves it (this server has no gateway to ask): one record the AEAT accepted with errors.
  const number = `E2E-AEAT-${RUN}`;
  psql(
    'insert into verifactu_aeatrecord (id, issuer_nif, environment, invoice_number, issue_date, fingerprint, state, csv, generated_on, queried_at) ' +
      `values (gen_random_uuid(), 'B12345674', 'testing', '${number}', '2026-10-14', '${'B'.repeat(64)}', 'AceptadoConErrores', 'CSV-${RUN}', now(), now())`,
  );
  await login(page, A, '/verifactu/recovery');
  const view = shown(page);
  await view.locator('[data-testid=verifactu-recovery-aeat-search] input').fill(`CSV-${RUN}`);
  const row = view.locator('[data-testid=verifactu-recovery-aeat-row]').filter({ hasText: number });
  await expect(row).toBeVisible();
  await expect(row).toContainText('Accepted with errors');
  await expect(view.locator('[data-testid=verifactu-recovery-aeat-row]')).toHaveCount(1);
  await flowShots(page, 'F27-photo', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-recovery-aeat-row]').filter({ hasText: number }).first());
  });
  await view.locator('[data-testid=verifactu-recovery-aeat-search] input').fill(`nothing-${RUN}`);
  await expect(view.locator('[data-testid=verifactu-recovery-aeat-empty]')).toContainText('No results');
});

test('VERIFACTU-F09–F12: Settings in two columns on a desk; back to testing, the connection test, the test invoice and the declaration', async ({ page }) => {
  // F09 is offered in production only: the configuration as going live leaves it, before any record of production.
  psql("update verifactu_config set environment = 'production', production_since = now()");
  await login(page, A, '/verifactu/settings');
  const view = shown(page);

  // As the old screen: «Sending» and «Responsible declaration» on the left, «Live test» on the right, on a desk;
  // one under the other on a phone.
  await page.setViewportSize({ width: 1440, height: 900 });
  const sending = view.locator('[data-testid=verifactu-settings-sending-card]');
  const live = view.locator('[data-testid=verifactu-settings-test-card]');
  const declaration = view.locator('[data-testid=verifactu-settings-declaration-card]');
  await expect(live).toBeVisible();
  /** Where each card is, once the page is laid out at this size. */
  const layout = async () => {
    const [s, l, d] = [await sending.boundingBox(), await live.boundingBox(), await declaration.boundingBox()];
    return {
      liveRightOfSending: l!.x >= s!.x + s!.width - 1,
      declarationUnderSending: Math.abs(d!.x - s!.x) < 2 && d!.y >= s!.y + s!.height - 1,
      liveUnderSending: l!.y >= s!.y + s!.height - 1,
    };
  };
  await expect.poll(layout).toEqual({ liveRightOfSending: true, declarationUnderSending: true, liveUnderSending: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(layout).toEqual({ liveRightOfSending: false, declarationUnderSending: true, liveUnderSending: true });
  await page.setViewportSize({ width: 1280, height: 860 });

  await view.locator('[data-testid=verifactu-settings-back]').click();
  const back = confirmation(page, 'Go back to the test environment?');
  await expect(back).toBeVisible();
  await flowShots(page, 'F09', async () => {
    await seen(back);
  });
  await back.locator('ion-button', { hasText: 'Back to testing' }).click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Your business is back in the test environment.' })).toBeVisible();
  await expect(view.locator('[data-testid=verifactu-settings-environment]')).toContainText('Testing (AEAT test)');

  // F10: the connection test presents nothing and says what is missing.
  await view.locator('[data-testid=verifactu-settings-test]').click();
  await expect(view.locator('[data-testid=verifactu-settings-result]')).toContainText("ERPlora's sending gateway is not configured on this server");
  await flowShots(page, 'F10', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-settings-result]'));
  });

  // F11: the test invoice is a real ticket of the test environment, with its record in Records.
  const created = page.waitForResponse((r) => r.url().endsWith('/api/verifactu/test_invoice') && r.request().method() === 'POST');
  await view.locator('[data-testid=verifactu-settings-test-invoice]').click();
  const answer = await created;
  expect(answer.status()).toBe(200);
  const out = (await answer.json()) as { invoice_id?: string; number?: string; record?: { invoice_id: string; invoice_number: string } };
  const invoiceId = out.record?.invoice_id ?? out.invoice_id ?? '';
  expect(invoiceId).not.toBe('');
  issuedIds.add(invoiceId);
  expect(psql(`select environment from verifactu_record where invoice_id = '${invoiceId}'`)).toBe('testing');
  await expect(page.locator('ion-toast').filter({ hasText: 'Test invoice' })).toBeVisible();
  await flowShots(page, 'F11', async (p) => {
    await seen(shown(p).locator('[data-testid=verifactu-settings-test-invoice]'));
  });

  // F12: the responsible declaration and the data that identify this system.
  await expect(view.locator('[data-testid=verifactu-settings-declaration]')).toHaveAttribute('target', '_blank');
  await expect(view.locator('[data-testid=verifactu-settings-identity]')).toContainText('ERPlora');
  await flowShots(page, 'F12', async (p) => {
    await shown(p).locator('[data-testid=verifactu-settings-identity]').scrollIntoViewIfNeeded();
    await expect(shown(p).locator('[data-testid=verifactu-settings-identity]')).toBeVisible();
  });
});

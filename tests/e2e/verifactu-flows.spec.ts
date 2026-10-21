// VeriFactu flow by flow (APP-VERIFACTU; apps/verifactu/WORKBOOK.md), in Chrome against the real Hub, Invoicing and
// Sales, no mocks. Each flow with a screen leaves its evidence in the three sizes of the migration
// (`APP-VERIFACTU-<flow>-390|834|1440` in `.artifacts`):
//   - VERIFACTU-F01: «My apps» opens VeriFactu on Records, with its six tabs;
//   - VERIFACTU-F16, F18: Records lists the run's record, found by its invoice, with «Verify at the AEAT»;
//   - VERIFACTU-F17, F25, F35: its record says why it waits; «Send now» and «Ask the AEAT» say why nothing reached
//     the AEAT (this server has no gateway), and the record stays in the queue;
//   - VERIFACTU-F24: a record the AEAT rejected says so and what to do, and «Correct» seals a new record;
//   - VERIFACTU-F30: «Cancel record» asks why before sealing the cancellation;
//   - VERIFACTU-F20, F21, F22: the queue lists what is not in the AEAT; «Process queue» and «Retry» answer;
//   - VERIFACTU-F31: Events tells what happened, the latest first;
//   - VERIFACTU-F26–F29: Recovery validates the chain, asks the AEAT and offers both recoveries, asking first;
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

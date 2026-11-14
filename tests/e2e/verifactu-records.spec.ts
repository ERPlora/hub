// VeriFactu in Chrome (apps/verifactu/WORKBOOK.md), against the real Invoicing and Sales, no mocks:
//   - VERIFACTU-F13, F16–F18: a ticket Invoicing issues is sealed inside its emission (its notice, delivered as the
//     outbox relay will, adds nothing), listed «Pending» with its QR, and its record says why it is not in the AEAT yet;
//   - VERIFACTU-F14: voiding a charged sale makes Invoicing issue an R5, registered as an alta (never an anulación);
//   - VERIFACTU-F30: a record issued by error is cancelled from its page with a chained cancellation record;
//   - VERIFACTU-F24: a rejection says in Records that it is still to correct (the funnel finds it); corrected from
//     its record, it says «Corrected» and links to the record that corrects it, in the list and in its page;
//   - VERIFACTU-F21, F10, F31: «Process queue» and «Test the connection» say that nothing can be presented without
//     ERPlora's gateway (it is never taken as accepted), and the audit trail tells it;
//   - Records and Events filter behind the table's funnel, with its count, at every width; the total is read as any
//     amount of the Hub («12,10 €», «1.000,50»); a total that is not an amount, or a day «until» before its «from», is
//     said under its field (the total with the money field's words) and does not filter.
// What this file creates is deleted after it (VeriFactu's rows first: a record keeps its invoice).
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, record as recordMetrics, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, issuedIds, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, shots, stamp } from './sale-helpers';

const RUN = stamp();
const STARTED = new Date().toISOString();
/** Whether the hub had VeriFactu's configuration row before the run (a run that made it removes it). */
let hadConfig = true;
let product: Product;

interface RecordOut {
  id: string;
  invoice_number: string;
  record_type: string;
  invoice_type: string;
  status: string;
  qr_url: string;
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/verifactu/records');
  snapshotSeries();
  await ensureIssuer(context);
  hadConfig = psql('select count(*) from verifactu_config') !== '0';
  product = await createProduct(context, { name: `E2E VeriFactu ${RUN}`, sku: `E2E-VF-${RUN}`, price: 1210, tax_category_key: 'product.generic' });
  await context.close();
});

/** VeriFactu's rows of the run's invoices go first (a record keeps its invoice), then the chain heads point back
 *  at what is left, and the audit events and the configuration the run made go too. */
function cleanVerifactu(): void {
  const invoices = `select id from invoice_invoice where id in (${[...issuedIds].map((id) => `'${id}'`).join(',') || `'00000000-0000-0000-0000-000000000000'`}) or source_sale_id in (select sale_id from sale_saleline where sku like 'E2E-VF-%')`;
  psql(
    [
      `create temp table e2e_vf as select id from verifactu_record where invoice_id in (${invoices})`,
      'update verifactu_chain set last_record_id = null where last_record_id in (select id from e2e_vf)',
      'update verifactu_record set previous_record_id = null where previous_record_id in (select id from e2e_vf)',
      `delete from verifactu_event where record_id in (select id from e2e_vf) or created_at >= '${STARTED}'`,
      'delete from verifactu_record where id in (select id from e2e_vf) and (cancels_id is not null or corrects_id is not null)',
      'delete from verifactu_record where id in (select id from e2e_vf)',
      'delete from verifactu_chain c where not exists (select 1 from verifactu_record r where r.issuer_nif = c.issuer_nif and r.environment = c.environment)',
      'delete from verifactu_sendcontrol s where not exists (select 1 from verifactu_record r where r.issuer_nif = s.issuer_nif and r.environment = s.environment)',
      `update verifactu_chain c set last_record_id = r.id, sequence = r.sequence, last_number = r.invoice_number, last_issue_date = r.issue_date, last_fingerprint = r.fingerprint, last_issuer_nif = r.issuer_nif
        from (select distinct on (issuer_nif, environment) * from verifactu_record order by issuer_nif, environment, sequence desc) r
        where r.issuer_nif = c.issuer_nif and r.environment = c.environment and c.last_record_id is null`,
      ...(hadConfig ? [] : ['delete from verifactu_config']),
    ].join('; '),
  );
}

test.afterAll(() => {
  try {
    cleanVerifactu();
  } finally {
    try {
      cleanInvoices();
    } finally {
      cleanSales();
      cleanInventory();
    }
  }
});

/** A ticket issued by hand through Invoicing's API (setup; the check is VeriFactu's). */
async function ticket(context: BrowserContext): Promise<{ id: string; number: string }> {
  const res = await api<{ id: string; number: string; verifactu_status: string | null }>(context, A, 'POST', '/invoice/invoices', {
    series_code: 'TICKET',
    lines: [{ description: `e2e VeriFactu ${RUN}`, quantity: '1', unit_price: 1000, tax_rate: '21' }],
  });
  expect(res.status, 'Invoicing issues the ticket').toBe(201);
  expect(res.data.verifactu_status, 'its record is sealed in the same commit').toBe('sealed');
  issuedIds.add(res.data.id);
  return res.data;
}

/** The record Invoicing's emission sealed: its real notice (read from the outbox), handed to VeriFactu as the relay
 * will, answers that same record and adds nothing. */
async function recordOf(context: BrowserContext, invoiceId: string): Promise<RecordOut> {
  const payload = psql(
    `select payload from live_outboxevent where name = 'invoice.invoice.issued' and payload->>'invoice_id' = '${invoiceId}' order by created_at desc, id desc limit 1`,
  );
  expect(payload, `invoice.invoice.issued of ${invoiceId} in the outbox`).not.toBe('');
  const res = await api<{ record: RecordOut; already: boolean }>(context, A, 'POST', '/verifactu/records', JSON.parse(payload));
  expect(res.status, 'VeriFactu answers its record').toBe(201);
  expect(res.data.already, 'the emission already sealed it').toBe(true);
  return res.data.record;
}

/** The fleet's three widths (`ui-clip-sweep.sh`): a desk, a tablet and a low phone; and a wide desk, where the table's
 *  Status column has room for the status and «Corrected» side by side. */
const CELL_VIEWPORTS = [
  { label: '1440', width: 1440, height: 900 },
  { label: '820', width: 820, height: 1180 },
  { label: '375', width: 375, height: 667 },
  { label: '1920', width: 1920, height: 1080 },
];

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Where a row's (or card's) status pill and its «Corrected» sit: the pill inside the link and the link's own box. */
async function correctionCell(row: Locator): Promise<{ status: Box; pill: Box; link: Box; underline: boolean }> {
  return row.evaluate((element) => {
    const box = (found: Element | null | undefined) => {
      if (!found) throw new Error('the status and «Corrected» are painted');
      const { x, y, width, height } = found.getBoundingClientRect();
      return { x, y, width, height };
    };
    const link = element.querySelector('[data-testid=verifactu-records-correction-corrected]');
    return {
      status: box(element.querySelector('[data-testid=verifactu-records-status]')),
      pill: box(link?.querySelector('.status-pill')),
      link: box(link),
      underline: link ? getComputedStyle(link).textDecorationLine !== 'none' : false,
    };
  });
}

/** The first box between `element` and its row that hides what overflows it (a focus ring past its edge would be cut),
 *  as `tag.class`; `null` when none does. */
function clippingAncestor(element: Element): string | null {
  for (let box = element.parentElement; box && !box.matches('[data-testid=verifactu-records-row]'); box = box.parentElement) {
    const { overflowX, overflowY } = getComputedStyle(box);
    if ([overflowX, overflowY].some((overflow) => overflow !== 'visible')) return `${box.tagName.toLowerCase()}.${box.className}`;
  }
  return null;
}

/** hub#865 - As the cell looked with the page's own sheet: the status and «Corrected» 4px apart, side by side and centred
 *  on one line (a card, a wide cell) or one under the other from the same left edge (a narrow cell); the link as tall
 *  as its pill, never a line of text around it that drops the pill below the status. */
function expectCorrectionBeside(
  { status, pill, link, underline }: { status: Box; pill: Box; link: Box; underline: boolean },
  at: string,
): 'side by side' | 'stacked' {
  const boxes = `${at}: ${JSON.stringify({ status, pill, link })}`;
  expect(underline, `«Corrected» is a pill, not underlined text (${at})`).toBe(false);
  const sideBySide = status.y < pill.y + pill.height && pill.y < status.y + status.height;
  if (sideBySide) {
    const gap = pill.x - (status.x + status.width);
    expect(gap, `side by side, 4px apart (${boxes})`).toBeGreaterThanOrEqual(3);
    expect(gap, `side by side, 4px apart (${boxes})`).toBeLessThanOrEqual(5);
    expect(Math.abs(status.y + status.height / 2 - (pill.y + pill.height / 2)), `centred on one line (${boxes})`).toBeLessThanOrEqual(1);
  } else {
    const gap = pill.y - (status.y + status.height);
    expect(gap, `one under the other, 4px apart (${boxes})`).toBeGreaterThanOrEqual(3);
    expect(gap, `one under the other, 4px apart (${boxes})`).toBeLessThanOrEqual(5);
    expect(Math.abs(pill.x - status.x), `from the same left edge (${boxes})`).toBeLessThanOrEqual(0.5);
  }
  expect(Math.abs(link.height - pill.height), `the link is as tall as its pill (${boxes})`).toBeLessThanOrEqual(0.5);
  expect(Math.abs(link.y - pill.y), `the link is as tall as its pill (${boxes})`).toBeLessThanOrEqual(0.5);
  return sideBySide ? 'side by side' : 'stacked';
}

async function openRecord(page: Page, record: RecordOut): Promise<void> {
  await page.goto(`${A}/verifactu/records/${record.id}`);
  await expect(shown(page).locator('[data-testid=verifactu-record-title]')).toHaveText(`Record ${record.invoice_number}`);
}

test('VERIFACTU-F13, F16–F18: an issued ticket is sealed, listed pending with its QR, and says why it waits', async ({ page, context }) => {
  await login(page, A, '/verifactu/records');
  const issued = await ticket(context);
  const record = await recordOf(context, issued.id);
  expect([record.record_type, record.invoice_type, record.status]).toEqual(['alta', 'F2', 'pending']);
  expect(record.qr_url).toContain('https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674');

  // The list follows itself: the new record shows without reloading, found by its invoice's number.
  const list = shown(page);
  await list.locator('[data-testid=verifactu-records-search] input').fill(issued.number);
  const row = list.locator('[data-testid=verifactu-records-row]').filter({ hasText: issued.number });
  await expect(row).toHaveCount(1);
  await expect(row.locator('[data-testid=verifactu-records-status]')).toHaveText('Pending');
  await shots(page, 'verifactu-records', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-records-search]')).toBeVisible();
  });

  await row.click();
  await expect(shown(page).locator('[data-testid=verifactu-record-title]')).toHaveText(`Record ${issued.number}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=verifactu-record-waiting]')).toContainText("ERPlora's sending gateway is not configured on this server");
  await expect(detail.locator('[data-testid=verifactu-record-qr]')).toBeVisible();
  await expect(detail.locator('[data-testid=verifactu-record-verify]')).toHaveAttribute('href', record.qr_url);
  await expect(detail.locator('[data-testid=verifactu-record-digest]')).toHaveText('Not stamped yet');
  await shots(page, 'verifactu-record', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-record-qr]')).toBeVisible();
  });
});

test('VERIFACTU-F14: voiding a charged sale registers its R5 as an alta, never as an anulación', async ({ page, context }) => {
  await login(page, A, '/verifactu/records');
  const sale = await chargeByApi(context, { lines: [{ product: product.sku }], payments: [{ method: 'card' }] });
  const ticketId = psql(`select id from invoice_invoice where source_sale_id = '${sale.id}' and source_type = 'sale'`);
  expect(ticketId, 'the till issued its ticket').not.toBe('');
  const first = await recordOf(context, ticketId);

  const voided = await api(context, A, 'POST', '/sale/sales/void', { sale_id: sale.id, reason: 'e2e wrong table' });
  expect(voided.status, 'the sale is voided').toBe(200);
  const r5 = psql(`select id from invoice_invoice where source_sale_id = '${sale.id}' and source_type = 'void'`);
  expect(r5, 'Invoicing issued its R5').not.toBe('');
  const record = await recordOf(context, r5);
  expect([record.record_type, record.invoice_type]).toEqual(['alta', 'R5']);

  await openRecord(page, record);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=verifactu-record-type]')).toHaveText('R5');
  await expect(detail.locator('[data-testid=verifactu-record-rectifies]')).toHaveText(first.invoice_number);
  await expect(detail.locator('[data-testid=verifactu-record-previous]')).toContainText(first.invoice_number);
});

test('VERIFACTU-F30: an invoice issued by error is cancelled from its record with a chained anulación', async ({ page, context }) => {
  await login(page, A, '/verifactu/records');
  const issued = await ticket(context);
  const record = await recordOf(context, issued.id);
  await openRecord(page, record);
  await shown(page).locator('[data-testid=verifactu-record-cancel]').click();
  const dialog = page.locator('ion-modal[data-testid=verifactu-cancel]:not(.overlay-hidden)');
  await expect(dialog).toBeVisible();
  await dialog.locator('[data-testid=verifactu-cancel-reason] textarea').fill('e2e duplicated ticket');
  await dialog.locator('[data-testid=verifactu-cancel-submit]').click();
  await expect(page.locator('ion-toast').filter({ hasText: `Cancellation of ${issued.number} sealed` })).toBeVisible();

  const both = await api<{ rows: RecordOut[] }>(context, A, 'GET', `/verifactu/records?search=${encodeURIComponent(issued.number)}&limit=10`);
  expect(both.data.rows.map((row) => row.record_type).sort()).toEqual(['alta', 'anulacion']);
  await page.goto(`${A}/verifactu/records`);
  const list = shown(page);
  await list.locator('[data-testid=verifactu-records-search] input').fill(issued.number);
  await expect(list.locator('[data-testid=verifactu-records-row]').filter({ hasText: 'Cancellation' })).toHaveCount(1);
});

test('VERIFACTU-F24: a rejection is listed «Pending correction» and, corrected from its record, links to its correction (hub#857)', async ({
  page,
  context,
}) => {
  await login(page, A, '/verifactu/records');
  const issued = await ticket(context);
  const record = await recordOf(context, issued.id);
  // The AEAT's rejection as its answer leaves the record (setup: nothing reaches the AEAT from a test).
  psql(`update verifactu_record set status = 'rejected', aeat_code = '1189', aeat_message = 'e2e rejected' where id = '${record.id}'`);
  const view = shown(page);
  const panel = view.locator('[data-testid=verifactu-records-filters-panel]');
  const toggle = view.locator('[data-testid=verifactu-records-filters-toggle]');
  const rejected = view.locator(`[data-testid=verifactu-records-row][data-id="${record.id}"]`);
  const search = async () => {
    await page.goto(`${A}/verifactu/records`);
    await view.locator('[data-testid=verifactu-records-search] input').fill(issued.number);
  };
  await search();
  await expect(rejected.locator('[data-testid=verifactu-records-status]')).toHaveText('Rejected');
  await expect(rejected.locator('[data-testid=verifactu-records-correction-pending]')).toHaveText('Pending correction');
  // «Correction» → «Pending correction» in the funnel keeps it.
  await toggle.click();
  await expect(panel).toBeVisible();
  await panel.locator('[data-testid=verifactu-records-filter-correction_status]').click();
  const popover = page.locator('ion-popover.select-popover');
  await popover.locator('ion-radio').filter({ hasText: /^\s*Pending correction\s*$/ }).click();
  await expect(popover).toHaveCount(0);
  await panel.locator('[data-testid=verifactu-records-filters-apply]').click();
  await expect(panel).toBeHidden();
  await expect(view.locator('[data-testid=verifactu-records-filters-count]')).toHaveText('1');
  await expect(rejected).toBeVisible();
  await shots(page, 'VERIFACTU-F24-records-pending', async (p) => {
    await expect(shown(p).locator(`[data-testid=verifactu-records-row][data-id="${record.id}"] [data-testid=verifactu-records-correction-pending]`)).toBeVisible();
  });

  // «Correct» from its record seals the correction; the rejection's page then links to it instead of what to do.
  await rejected.click();
  await expect(page).toHaveURL(new RegExp(`/verifactu/records/${record.id}$`));
  const detail = shown(page);
  await detail.locator('[data-testid=verifactu-record-correct]').click();
  const confirm = page.locator('.ep-confirm-dialog').last();
  await expect(confirm).toContainText(`Correct the record of ${issued.number}?`);
  await confirm.getByRole('button', { name: 'Correct' }).click();
  await expect(page.locator('ion-toast').filter({ hasText: `Correction of ${issued.number} sealed` })).toBeVisible();
  const both = await api<{ rows: (RecordOut & { correction_status: string; corrected_by_id: string | null })[] }>(
    context,
    A,
    'GET',
    `/verifactu/records?search=${encodeURIComponent(issued.number)}&limit=10`,
  );
  const correction = both.data.rows.find((row) => row.id !== record.id);
  expect(correction, 'the correction is a new record of the same invoice').toBeDefined();
  expect(both.data.rows.find((row) => row.id === record.id)).toMatchObject({ correction_status: 'corrected', corrected_by_id: correction?.id });
  const corrected = detail.locator('[data-testid=verifactu-record-corrected]');
  await expect(corrected).toContainText('Already corrected with a new record');
  await expect(detail.locator('[data-testid=verifactu-record-rejected]')).not.toContainText('rectify it in Invoicing');
  await shots(page, 'VERIFACTU-F24-record-corrected', async (p) => {
    // The page is still scrolled down to «Correct»: the notice is at its top.
    const notice = shown(p).locator('[data-testid=verifactu-record-corrected]');
    await notice.scrollIntoViewIfNeeded();
    await expect(notice).toBeInViewport();
  });
  await detail.locator('[data-testid=verifactu-record-corrected-link]').click();
  await expect(page).toHaveURL(new RegExp(`/verifactu/records/${correction?.id}$`));

  // In Records: no longer pending (the funnel leaves it out); «Corrected» opens the correction, not the rejection.
  await search();
  await expect(rejected.locator('[data-testid=verifactu-records-correction-pending]')).toHaveCount(0);
  const link = rejected.locator('[data-testid=verifactu-records-correction-corrected]');
  await expect(link).toHaveText('Corrected');
  // hub#865: the status and «Corrected» beside it, at the three widths: apart, on one line and centred on it (or one
  // under the other), and the link as tall as its pill.
  const layouts: string[] = [];
  for (const viewport of CELL_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await expect(link).toBeVisible();
    await link.scrollIntoViewIfNeeded();
    const cell = await correctionCell(rejected);
    recordMetrics(`hub-865-records-corrected-${viewport.label}`, cell);
    layouts.push(expectCorrectionBeside(cell, viewport.label));
    await capture(page, `VERIFACTU-F24-records-corrected-${viewport.label}`);
  }
  // Both ways are measured: a narrow table cell stacks them (1440), a card and the wide cell put them side by side.
  expect(layouts).toEqual(['stacked', 'side by side', 'side by side', 'side by side']);
  await page.setViewportSize({ width: 1440, height: 900 });
  // From the keyboard: Tab from its row reaches «Corrected», and Space opens the record that corrects it, as the click
  // and Enter do, never the rejected one of its row (which opens on Enter and Space).
  await rejected.focus();
  await page.keyboard.press('Tab');
  await expect(link).toBeFocused();
  // Its focus ring shows whole: no box around the link cuts it (the page's own sheet once left it clipped in the cell).
  expect(await link.evaluate((element) => getComputedStyle(element).outlineStyle), 'the focused link draws its ring').not.toBe('none');
  expect(await link.evaluate(clippingAncestor), 'nothing between the link and its row cuts its ring').toBeNull();
  await capture(page, 'VERIFACTU-F24-records-corrected-focused-1440');
  await page.keyboard.press('Space');
  await expect(page).toHaveURL(new RegExp(`/verifactu/records/${correction?.id}$`));
  await search();
  await link.press('Enter');
  await expect(page).toHaveURL(new RegExp(`/verifactu/records/${correction?.id}$`));
  await search();
  await link.click();
  await expect(page).toHaveURL(new RegExp(`/verifactu/records/${correction?.id}$`));
  await search();
  await toggle.click();
  await panel.locator('[data-testid=verifactu-records-filter-correction_status]').click();
  await popover.locator('ion-radio').filter({ hasText: /^\s*Pending correction\s*$/ }).click();
  await expect(popover).toHaveCount(0);
  await panel.locator('[data-testid=verifactu-records-filters-apply]').click();
  await expect(rejected).toHaveCount(0);
  await expect(view.locator('[data-testid=verifactu-records-empty]')).toBeVisible();
});

test('VERIFACTU-F21, F10 and F31: without the gateway nothing is presented, and the audit trail says so', async ({ page }) => {
  await login(page, A, '/verifactu/contingency');
  await shown(page).locator('[data-testid=verifactu-queue-process]').click();
  await expect(shown(page).locator('[data-testid=verifactu-queue-result]')).toHaveText("ERPlora's sending gateway is not configured on this server");
  await shots(page, 'verifactu-contingency', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-queue-search]')).toBeVisible();
  });

  await page.goto(`${A}/verifactu/settings`);
  await shown(page).locator('[data-testid=verifactu-settings-test]').click();
  const result = shown(page).locator('[data-testid=verifactu-settings-result]');
  await expect(result).toContainText('It cannot send yet:');
  await expect(result).toContainText("ERPlora's sending gateway is not configured on this server");
  await shots(page, 'verifactu-settings', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-settings-result]')).toBeVisible();
  });

  await page.goto(`${A}/verifactu/events`);
  const events = shown(page);
  await events.locator('[data-testid=verifactu-events-search] input').fill('Connection test');
  await expect(events.locator('[data-testid=verifactu-events-row]').first()).toContainText('Connection test');
});

/** The widths of the filter panel's screenshots: a phone (the panel is a sheet), a tablet and a desk (two
 *  columns), as the SaaS panel's `VIEWPORTS`. */
const FILTER_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** `YYYY-MM-DD` of the local day `days` from today (the business's clock is the machine's in local runs). */
function localDay(days = 0): string {
  const day = new Date();
  day.setDate(day.getDate() + days);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
}

// flow: none — the column filters sit behind the table's funnel.
test('Records filter by Date and Total (euros) behind the funnel, with its count, the panel open at every width; a wrong total or day is said under it', async ({
  page,
  context,
}) => {
  await login(page, A, '/verifactu/records');
  const issued = await ticket(context);
  const view = shown(page);
  const panel = view.locator('[data-testid=verifactu-records-filters-panel]');
  const toggle = view.locator('[data-testid=verifactu-records-filters-toggle]');
  const count = view.locator('[data-testid=verifactu-records-filters-count]');
  const box = (name: string) => panel.locator(`[data-testid=verifactu-records-filter-${name}] input`);
  const row = view.locator('[data-testid=verifactu-records-row]').filter({ hasText: issued.number });
  for (const vp of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/verifactu/records`);
    await view.locator('[data-testid=verifactu-records-search] input').fill(issued.number);
    await expect(row).toBeVisible();
    await toggle.click();
    await expect(panel).toBeVisible();
    await box('issue_date_from').fill(localDay());
    await box('issue_date_to').fill(localDay());
    // «12,10» as typed: euros, sent as 1210 cents.
    await box('total_amount_from').fill('12,10');
    await box('total_amount_to').fill('12,10');
    await panel.locator('[data-testid=verifactu-records-filters-apply]').click();
    await expect(panel).toBeHidden();
    await expect(count).toHaveText('2');
    await expect(row).toBeVisible();
    await toggle.click();
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-FILTERS-2B-verifactu-${vp.label}`) });
    // A cent more than its total leaves it out.
    await box('total_amount_from').fill('12,11');
    await panel.locator('[data-testid=verifactu-records-filters-apply]').click();
    await expect(row).toHaveCount(0);
    await expect(view.locator('[data-testid=verifactu-records-empty]')).toBeVisible();
    await toggle.click();
    await panel.locator('[data-testid=verifactu-records-filters-clear]').click();
    await expect(count).toHaveCount(0);
    await panel.locator('[data-testid=verifactu-records-filters-close]').click();
    await expect(panel).toBeHidden();
    await expect(row).toBeVisible();
  }
  // The total is read as any amount of the Hub (hub#1247): «12,10 €» and «1.000,50» filter and nothing is said.
  await toggle.click();
  await box('total_amount_from').fill('12,10 €');
  await box('total_amount_to').fill('1.000,50');
  await panel.locator('[data-testid=verifactu-records-filters-apply]').click();
  await expect(panel).toBeHidden();
  await expect(toggle).not.toHaveAttribute('data-invalid', 'true');
  await expect(count).toHaveText('2');
  await expect(row).toBeVisible();
  // From 1.000,50 € on, its 12,10 € ticket is left out.
  await toggle.click();
  await box('total_amount_from').fill('1.000,50');
  await box('total_amount_to').fill('');
  await panel.locator('[data-testid=verifactu-records-filters-apply]').click();
  await expect(count).toHaveText('1');
  await expect(row).toHaveCount(0);
  await toggle.click();
  await panel.locator('[data-testid=verifactu-records-filters-clear]').click();
  await expect(count).toHaveCount(0);
  await panel.locator('[data-testid=verifactu-records-filters-close]').click();
  await expect(row).toBeVisible();
  // A total that is not an amount and a day «until» before its «from»: the funnel says so, each field says why,
  // and neither filters (the «from» day still does).
  await toggle.click();
  await box('total_amount_from').fill('12x');
  await box('issue_date_from').fill(localDay());
  await box('issue_date_to').fill(localDay(-1));
  await panel.locator('[data-testid=verifactu-records-filters-apply]').click();
  await expect(toggle).toHaveAttribute('data-invalid', 'true');
  await expect(row).toBeVisible();
  await toggle.click();
  await expect(panel.getByText('This is not an amount. Type a figure, for example 12.50.')).toBeVisible();
  await expect(panel.getByText('The end date cannot be before the start date.')).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: shot('FIX-DATATABLE-HUB-FILTERS-2B-verifactu-error') });
  await panel.locator('[data-testid=verifactu-records-filters-clear]').click();
  await expect(count).toHaveCount(0);
});

// flow: none — the column filters sit behind the table's funnel.
test('Events filter by Type and day behind the funnel, with its count; a day «until» before its «from» is said under it', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/verifactu/events');
  await ticket(context);
  await page.goto(`${A}/verifactu/events`);
  const view = shown(page);
  const panel = view.locator('[data-testid=verifactu-events-filters-panel]');
  const toggle = view.locator('[data-testid=verifactu-events-filters-toggle]');
  const count = view.locator('[data-testid=verifactu-events-filters-count]');
  const rows = view.locator('[data-testid=verifactu-events-row]');
  const box = (name: string) => panel.locator(`[data-testid=verifactu-events-filter-${name}] input`);
  await expect(rows.first()).toBeVisible();
  await toggle.click();
  await expect(panel).toBeVisible();
  await panel.locator('[data-testid=verifactu-events-filter-kind]').click();
  const popover = page.locator('ion-popover.select-popover');
  await popover.locator('ion-radio').filter({ hasText: /^\s*Record created\s*$/ }).click();
  await expect(popover).toHaveCount(0);
  await box('date_from').fill(localDay());
  await box('date_to').fill(localDay());
  await panel.locator('[data-testid=verifactu-events-filters-apply]').click();
  await expect(panel).toBeHidden();
  await expect(count).toHaveText('2');
  await expect(rows.first()).toContainText('Record created');
  await expect(rows.filter({ hasNotText: 'Record created' })).toHaveCount(0);
  // The day «until» before its «from».
  await toggle.click();
  await box('date_to').fill(localDay(-1));
  await panel.locator('[data-testid=verifactu-events-filters-apply]').click();
  await expect(toggle).toHaveAttribute('data-invalid', 'true');
  await expect(rows.first()).toContainText('Record created');
  await toggle.click();
  await expect(panel.getByText('The end date cannot be before the start date.')).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: shot('FIX-DATATABLE-HUB-FILTERS-2B-verifactu-events-1440') });
  await panel.locator('[data-testid=verifactu-events-filters-clear]').click();
  await expect(count).toHaveCount(0);
});

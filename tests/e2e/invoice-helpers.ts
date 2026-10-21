// Shared steps of the Invoicing browser specs (apps/invoice/WORKBOOK.md): the issuer set up through the
// app's API (setup, never the check itself), the delivery of a Sales event to Invoicing as the outbox relay
// will in phase 2 (the event's real payload, read from the outbox, posted to the operation the reaction
// runs), and the cleanup every invoice spec runs in its `afterAll` BEFORE Sales' (a document keeps its sale).
// What a run creates is found by its sales (`E2E-INV-…` products), its names (`e2e …`), its series
// (`E2E…` codes) or the ids it recorded.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, psql, shot } from './helpers';

/** The three sizes of a flow's evidence (the migration's: 390×844, 834×1112, 1440×900). */
export const FLOW_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** The page in the three sizes, as `APP-INVOICE-<flow>-<size>` in `.artifacts`, each once `ready` says it painted;
 *  the size the spec had comes back after. */
export async function flowShots(page: Page, flow: string, ready: (page: Page) => Promise<void>): Promise<void> {
  const restore = page.viewportSize() ?? { width: 1280, height: 860 };
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await page.screenshot({ path: shot(`APP-INVOICE-${flow}-${viewport.label}`) });
  }
  await page.setViewportSize(restore);
}

/** The dialog `testid` that is open now: Ionic keeps each page of the stack mounted, with its own (hidden)
 *  copy of the same dialog. */
export const openDialog = (page: Page, testid: string): Locator => page.locator(`ion-modal[data-testid=${testid}]:not(.overlay-hidden)`);

/** Ids of the documents a spec issued (to clean up whatever their names say). */
export const issuedIds = new Set<string>();
/** The issuer this run had to set up (it is removed after); `false` while it found one. */
let setUpIssuer = false;
/** Each series' counter before the spec (`id:current_number`), to give back the numbers it used. */
let seriesBefore: string[] | null = null;
/** Whether VeriFactu's configuration row existed before the spec (issuing seals a record, which makes it). */
let hadVerifactuConfig = true;

/** Notes every series' counter, so `cleanInvoices()` gives the numbering back as it found it. Call it in
 *  `beforeAll`, before anything is issued. */
export function snapshotSeries(): void {
  hadVerifactuConfig = psql('select count(*) from verifactu_config') !== '0';
  seriesBefore = psql(`select string_agg(id::text || ':' || current_number::text, ',') from invoice_invoiceseries`)
    .split(',')
    .filter(Boolean);
}

export interface IssuerOut {
  configured: boolean;
  legal_name: string;
  tax_id: string;
  address: string;
  postal_code: string;
  city: string;
  province: string;
  country: string;
  source: string;
}

/** The hub's issuer now (server-side evidence, and what a spec that edits it gives back after). */
export async function issuerNow(context: BrowserContext): Promise<IssuerOut> {
  const res = await api<IssuerOut>(context, A, 'GET', '/invoice/issuer');
  expect(res.status).toBe(200);
  return res.data;
}

/** After a spec saved the issuer through its page: the hub's own goes back as it was, or, when the hub
 *  had none, `cleanInvoices()` removes the one the run saved. */
export async function restoreIssuer(context: BrowserContext, original: IssuerOut): Promise<void> {
  if (!original.configured) {
    setUpIssuer = true;
    return;
  }
  const { legal_name, tax_id, address, postal_code, city, province, country } = original;
  const res = await api(context, A, 'POST', '/invoice/issuer', { legal_name, tax_id, address, postal_code, city, province, country });
  expect(res.status, 'the issuer back as it was').toBe(200);
}

/** The issuer, set up as the owner would when the hub has none (Invoicing → Issuer). */
export async function ensureIssuer(context: BrowserContext): Promise<IssuerOut> {
  const current = await issuerNow(context);
  if (current.configured) return current;
  const saved = await api<IssuerOut>(context, A, 'POST', '/invoice/issuer', {
    legal_name: 'e2e Peluquería Ana SL',
    tax_id: 'B12345674',
    address: 'Calle Mayor 1',
    postal_code: '28001',
    city: 'Madrid',
    province: 'Madrid',
    country: 'ES',
  });
  expect(saved.status).toBe(200);
  setUpIssuer = true;
  return saved.data;
}

export interface InvoiceLink {
  id: string;
  number: string;
  status: string;
}

export interface InvoiceOut extends InvoiceLink {
  invoice_type: string;
  total_amount: number;
  customer_name: string;
  customer_tax_id: string;
  rectifies: InvoiceLink | null;
  substitutes: InvoiceLink | null;
  substituted_by: InvoiceLink | null;
  rectifications: InvoiceLink[];
}

interface IssueOut {
  issued: boolean;
  already: boolean;
  invoice: InvoiceOut | null;
}

/** The operation each Sales event is delivered to (apps/invoice/events.py `REACTIONS`), by its route. */
const REACTION_ROUTES: Record<string, string> = {
  'sale.sale.completed': '/invoice/invoices/from_sale',
  'sale.sale.refunded': '/invoice/invoices/rectify_from_refund',
  'sale.sale.voided': '/invoice/invoices/rectify_from_void',
};

/** Hands the newest `name` event of `saleId` to Invoicing, as the relay will: its real payload, read from
 *  the outbox, to the operation that reacts to it. Returns the document it issued. */
export async function deliver(context: BrowserContext, name: keyof typeof REACTION_ROUTES & string, saleId: string): Promise<InvoiceOut> {
  const payload = psql(
    `select payload from live_outboxevent where name = '${name}' and payload->>'sale_id' = '${saleId}' order by created_at desc, id desc limit 1`,
  );
  expect(payload, `${name} of ${saleId} in the outbox`).not.toBe('');
  const res = await api<IssueOut>(context, A, 'POST', REACTION_ROUTES[name], JSON.parse(payload));
  expect(res.status, `${name} → ${REACTION_ROUTES[name]}`).toBe(200);
  expect(res.data.invoice, `${name} issued a document`).not.toBeNull();
  issuedIds.add(res.data.invoice!.id);
  return res.data.invoice!;
}

/** A document read back (server-side evidence). */
export async function invoiceOf(context: BrowserContext, id: string): Promise<InvoiceOut> {
  const res = await api<InvoiceOut>(context, A, 'GET', `/invoice/invoices/detail?invoice_id=${id}`);
  expect(res.status).toBe(200);
  return res.data;
}

const LINKED_TO_THEM =
  'insert into e2e_inv select id from invoice_invoice where rectifies_id in (select id from e2e_inv) or substitutes_id in (select id from e2e_inv) on conflict do nothing';
const UNREFERENCED =
  'delete from invoice_invoice where id in (select id from e2e_inv) and id not in (select rectifies_id from invoice_invoice where rectifies_id is not null) and id not in (select substitutes_id from invoice_invoice where substitutes_id is not null)';

/** Deletes the documents a run issued (and every document that rectifies or replaces one of them), the
 *  run's series and the issuer the run set up, and gives each series' counter back where the snapshot
 *  found it when nothing newer was numbered in it meanwhile (a factory series the run opened goes too).
 *  Run it BEFORE `cleanSales()`. */
export function cleanInvoices(): void {
  const recorded = [...issuedIds].map((id) => `'${id}'`).join(',') || `'00000000-0000-0000-0000-000000000000'`;
  const before = (seriesBefore ?? []).map((entry) => {
    const [id, number] = entry.split(':');
    return `('${id}'::uuid, ${Number(number)})`;
  });
  psql(
    [
      'create temp table e2e_inv (id uuid primary key)',
      'create temp table e2e_before (id uuid primary key, n integer)',
      ...(before.length ? [`insert into e2e_before values ${before.join(',')}`] : []),
      `insert into e2e_inv select id from invoice_invoice where id in (${recorded}) or customer_name like 'e2e%' or notes like 'e2e %' or series_code like 'E2E%' or source_sale_id in (select sale_id from sale_saleline where sku like 'E2E-INV-%') on conflict do nothing`,
      // What rectifies or replaces them (a rectifying invoice of the F3 of a ticket is two steps away).
      ...Array.from({ length: 3 }, () => LINKED_TO_THEM),
      // VeriFactu's records of those documents go first (a record keeps its invoice: PROTECT); its chain heads
      // then point back at what is left, as VeriFactu's own spec leaves them.
      'create temp table e2e_vf as select id from verifactu_record where invoice_id in (select id from e2e_inv)',
      'update verifactu_chain set last_record_id = null where last_record_id in (select id from e2e_vf)',
      'update verifactu_record set previous_record_id = null where previous_record_id in (select id from e2e_vf)',
      'delete from verifactu_event where record_id in (select id from e2e_vf)',
      'delete from verifactu_record where id in (select id from e2e_vf) and (cancels_id is not null or corrects_id is not null)',
      'delete from verifactu_record where id in (select id from e2e_vf)',
      'delete from verifactu_chain c where not exists (select 1 from verifactu_record r where r.issuer_nif = c.issuer_nif and r.environment = c.environment)',
      'delete from verifactu_sendcontrol s where not exists (select 1 from verifactu_record r where r.issuer_nif = s.issuer_nif and r.environment = s.environment)',
      `update verifactu_chain c set last_record_id = r.id, sequence = r.sequence, last_number = r.invoice_number, last_issue_date = r.issue_date, last_fingerprint = r.fingerprint, last_issuer_nif = r.issuer_nif
        from (select distinct on (issuer_nif, environment) * from verifactu_record order by issuer_nif, environment, sequence desc) r
        where r.issuer_nif = c.issuer_nif and r.environment = c.environment and c.last_record_id is null`,
      ...(hadVerifactuConfig ? [] : ['delete from verifactu_config where not exists (select 1 from verifactu_record)']),
      'delete from invoice_invoiceline where invoice_id in (select id from e2e_inv)',
      // A document goes once nothing points at it (a rectifying one is always linked): from the last link back.
      ...Array.from({ length: 4 }, () => UNREFERENCED),
      `delete from invoice_invoiceseries where code like 'E2E%'`,
      'update invoice_invoiceseries s set current_number = b.n from e2e_before b where s.id = b.id and s.current_number > b.n and not exists (select 1 from invoice_invoice i where i.series_id = s.id and i.sequence > b.n)',
      ...(seriesBefore !== null
        ? [`delete from invoice_invoiceseries s where s.id not in (select id from e2e_before) and s.code in ('FACT', 'TICKET', 'RECT') and not exists (select 1 from invoice_invoice i where i.series_id = s.id)`]
        : []),
      ...(setUpIssuer ? [`delete from invoice_issuer where legal_name like 'e2e %'`] : []),
    ].join('; '),
  );
  issuedIds.clear();
  setUpIssuer = false;
  seriesBefore = null;
  hadVerifactuConfig = true;
}

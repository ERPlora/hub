// Shared steps of the Sales & POS browser specs (apps/sale/WORKBOOK.md): setup through the real apps'
// APIs (Inventory's products, Customers' cards, the charge itself) — evidence and setup, never the check
// itself — the three viewports' screenshots, the cash register switched off for the specs that are not
// about it (SALE-F08: with it on and no session, no cash), and the cleanup every sale spec runs in its
// `afterAll` (the fiscal documents Invoicing issued for its sales go first: a document keeps its sale).
// What a run creates is named `E2E-…` (products), `e2e.…` (customers) or `e2e …` (departments, quick
// notes, check titles); its sales are found by their lines.
import { type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, psql, shot } from './helpers';
import { cleanInvoices, issuedIds } from './invoice-helpers';

export const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

/** A unique suffix for this run's data. */
export const stamp = (): string => `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`.toUpperCase();

export interface SaleOut {
  id: string;
  number: string;
  status: string;
  total: number;
  subtotal: number;
  tax_total: number;
  change_total: number;
  customer_id: string | null;
  customer_name: string;
  /** Its fiscal document in Invoicing (none while it waits or without Invoicing) and that document's number. */
  invoice_id: string | null;
  invoice_number: string;
  lines: {
    id: string;
    name: string;
    sku: string;
    quantity: string;
    tax_rate: string;
    net_amount: number;
    tax_amount: number;
    line_total: number;
  }[];
  payments: { id: string; method_type: string; amount: number; tendered: number; change: number }[];
}

/** A charge through the API (setup for the history specs; the till's own charge is checked in the browser). */
export async function chargeByApi(context: BrowserContext, body: Record<string, unknown>): Promise<SaleOut> {
  const res = await api<SaleOut>(context, A, 'POST', '/sale/sales', { idempotency_key: `e2e-${stamp()}`, ...body });
  expect(res.status, `charge ${JSON.stringify(body)}`).toBe(201);
  return res.data;
}

/** The sale charged with `key`, read back (server-side evidence). */
export async function saleByKey(context: BrowserContext, key: string): Promise<SaleOut | null> {
  const res = await api<{ found: boolean; sale: SaleOut | null }>(context, A, 'GET', `/sale/sales/by_key?idempotency_key=${encodeURIComponent(key)}`);
  return res.data?.sale ?? null;
}

/** The newest sale that sold `sku` (server-side evidence of what the till charged). By the run's own
 *  SKU, never «the hub's last sale»: another session may be charging on the same hub at once. */
export async function newestSaleOf(context: BrowserContext, sku: string): Promise<SaleOut> {
  const page = await api<{ rows: { id: string }[] }>(context, A, 'GET', '/sale/sales?limit=50');
  for (const row of page.data.rows) {
    const sale = (await api<SaleOut>(context, A, 'GET', `/sale/sales/detail?sale_id=${row.id}`)).data;
    if (sale.lines.some((line) => line.sku === sku)) return sale;
  }
  throw new Error(`no recent sale sold ${sku}`);
}

/** Screenshots of the page in the three viewports, each once `ready` says it painted. */
export async function shots(page: Page, name: string, ready: (page: Page) => Promise<void>, restore = { width: 1280, height: 860 }): Promise<void> {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await page.screenshot({ path: shot(`${name}-${viewport.label}`) });
  }
  await page.setViewportSize(restore);
}

/** Whether the cash register was on before a spec switched it off (`null`: the spec did not touch it). */
let drawerWasOn: boolean | null = null;

/** The specs that are not about the drawer sell cash without opening a session: the cash register goes
 *  off for them (Cash register → Settings), and `restoreDrawer()` gives it back as it was. */
export async function drawerOff(context: BrowserContext): Promise<void> {
  const settings = await api<{ enable_cash_register: boolean }>(context, A, 'GET', '/cash_register/settings');
  expect(settings.status).toBe(200);
  drawerWasOn = settings.data.enable_cash_register;
  if (drawerWasOn) {
    const off = await api(context, A, 'POST', '/cash_register/settings', { enable_cash_register: false });
    expect(off.status, 'cash register off for the spec').toBe(200);
  }
}

/** The cash register back as `drawerOff()` found it. */
export function restoreDrawer(): void {
  if (drawerWasOn) psql('update cash_register_settings set enable_cash_register = true');
  drawerWasOn = null;
}

/** The e2e checks: their lines name an `E2E-` product or an `e2e ` department, or their title is `e2e …`. */
const E2E_ORDERS =
  "select distinct order_id as id from sale_orderline where sku like 'E2E-%' or name like 'e2e %' union select id from sale_order where label like 'e2e %'";

/** Deletes the fiscal documents Invoicing issued for the sales of the checks `orders` (a SELECT of their
 *  ids) — their tickets, invoices and rectifying invoices —, with Invoicing's own cleanup. Run it before
 *  deleting those sales. */
export function cleanDocumentsOf(orders: string): void {
  const sales = `select id from sale_sale where order_id in (${orders})`;
  const documents = psql(
    `select string_agg(id::text, ',') from invoice_invoice where source_sale_id in (${sales}) or source_refund_id in (select id from sale_refund where sale_id in (${sales}))`,
  );
  for (const id of documents.split(',').filter(Boolean)) issuedIds.add(id);
  cleanInvoices();
}

/** Deletes the sales and checks a run made (their lines name an `E2E-` product, an `e2e ` department or
 *  the check's title is `e2e …`), their lines in a cash shift, the paper they asked of Printing (and the
 *  kitchen's sheets of their checks), the kitchen tickets of their rounds, the fiscal documents Invoicing issued for them in the same charge, void
 *  or refund (with Invoicing's own cleanup, which gives the series' numbers back), and the `e2e `
 *  departments and quick notes. Run it BEFORE the customer and inventory cleanups: a sale keeps its
 *  customer's card. */
export function cleanSales(): void {
  cleanDocumentsOf(E2E_ORDERS);
  psql(
    [
      `create temp table e2e_orders as ${E2E_ORDERS}`,
      'create temp table e2e_sales as select id from sale_sale where order_id in (select id from e2e_orders)',
      // The paper their charges, reprints and bills asked of Printing, and the kitchen's sheets of their checks
      // (job keys `sale-<sale>-…`, `sale-order-<check>-…`, `kitchen-<ticket>-…`): a sheet left waiting without
      // a printer is the next one a device takes in another spec.
      `delete from printing_printjob where job_key like any (array(
        select 'sale-' || id || '-%' from e2e_sales
        union all select 'sale-order-' || id || '-%' from e2e_orders
        union all select 'kitchen-' || ticket_id || '-%' from kitchen_ticketitem
          where sale_line_id in (select id from sale_orderline where order_id in (select id from e2e_orders))))`,
      // The kitchen tickets of their rounds, their dishes and their History: only the tickets of these checks (by
      // the check or by one of its lines), never one made by hand or by another spec's check.
      `create temp table e2e_kitchen as select id from kitchen_ticket where order_id in (select id from e2e_orders)
        union select ticket_id from kitchen_ticketitem
          where sale_line_id in (select id from sale_orderline where order_id in (select id from e2e_orders))`,
      'delete from kitchen_logentry where ticket_id in (select id from e2e_kitchen)',
      'delete from kitchen_ticketitem where ticket_id in (select id from e2e_kitchen)',
      'delete from kitchen_ticket where id in (select id from e2e_kitchen)',
      // A sale charged in cash with a drawer open has its line in the shift (a run that stopped before its own
      // cleanup leaves it): it goes first, or it holds its sale, payment and refund.
      `delete from cash_register_movement where sale_id in (select id from e2e_sales)
        or sale_payment_id in (select id from sale_salepayment where sale_id in (select id from e2e_sales))
        or refund_payment_id in (select id from sale_refundpayment where refund_id in (select id from sale_refund where sale_id in (select id from e2e_sales)))`,
      'delete from sale_refundline where refund_id in (select id from sale_refund where sale_id in (select id from e2e_sales))',
      'delete from sale_refundpayment where refund_id in (select id from sale_refund where sale_id in (select id from e2e_sales))',
      'delete from sale_refund where sale_id in (select id from e2e_sales)',
      'delete from sale_orderline where order_id in (select id from e2e_orders)',
      'delete from sale_salepayment where sale_id in (select id from e2e_sales)',
      'delete from sale_saleline where sale_id in (select id from e2e_sales)',
      'delete from sale_sale where id in (select id from e2e_sales)',
      'delete from sale_order where id in (select id from e2e_orders)',
      "delete from sale_department where name like 'e2e %'",
      "delete from sale_quicknote where text like 'e2e %'",
    ].join('; '),
  );
}

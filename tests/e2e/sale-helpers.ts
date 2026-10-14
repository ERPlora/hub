// Shared steps of the Sales & POS browser specs (apps/sale/WORKBOOK.md): setup through the real apps'
// APIs (Inventory's products, Customers' cards, the charge itself) — evidence and setup, never the check
// itself — the three viewports' screenshots, and the cleanup every sale spec runs in its `afterAll`.
// What a run creates is named `E2E-…` (products), `e2e.…` (customers) or `e2e …` (departments, quick
// notes, check titles); its sales are found by their lines.
import { type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, psql, shot } from './helpers';

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
  lines: { id: string; name: string; tax_rate: string; net_amount: number; tax_amount: number; line_total: number }[];
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

/** The newest sale of this hub (server-side evidence of what the till charged). */
export async function newestSale(context: BrowserContext): Promise<SaleOut> {
  const page = await api<{ rows: { id: string }[] }>(context, A, 'GET', '/sale/sales?limit=1');
  const res = await api<SaleOut>(context, A, 'GET', `/sale/sales/detail?sale_id=${page.data.rows[0].id}`);
  return res.data;
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

/** Deletes the sales and checks a run made (their lines name an `E2E-` product, an `e2e ` department or
 *  the check's title is `e2e …`), and the `e2e ` departments and quick notes. Run it BEFORE the customer
 *  and inventory cleanups: a sale keeps its customer's card. */
export function cleanSales(): void {
  psql(
    [
      "create temp table e2e_orders as select distinct order_id as id from sale_orderline where sku like 'E2E-%' or name like 'e2e %' union select id from sale_order where label like 'e2e %'",
      'create temp table e2e_sales as select id from sale_sale where order_id in (select id from e2e_orders)',
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

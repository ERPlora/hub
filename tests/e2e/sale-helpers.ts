// Shared steps of the Sales & POS browser specs (apps/sale/WORKBOOK.md): setup through the real apps'
// APIs (Inventory's products, Customers' cards, the charge itself) — evidence and setup, never the check
// itself — the three viewports' screenshots, the cash register switched off for the specs that are not
// about it (SALE-F08: with it on and no session, no cash), and the cleanup every sale spec runs in its
// `afterAll` (the fiscal documents Invoicing issued for its sales go first: a document keeps its sale).
// What a run creates is named `E2E-…` (products), `e2e.…` (customers) or `e2e …` (departments, quick
// notes, check titles); its sales are found by their lines.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { createProduct, type Product } from './inventory-helpers';
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
  /** The currency it was charged in (the business's then) and its decimals. */
  currency: string;
  currency_decimals: number;
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

/** When the till is a phone's: the catalogue alone and the check a drawer behind the cart button. The rule of
 *  `apps/sale/frontend/pages/PosPage.vue` (`PHONE`, `NARROW_TILL`): this window, or a till narrower than that. */
const TILL_PHONE = { media: '(max-width: 820px), (max-height: 500px)', narrowerThan: 700 };

/**
 * Whether the till on screen is a phone's, once it has laid itself out for the window. It does so a frame after a
 * resize (its media query and its ResizeObserver): read straight after `setViewportSize`, the cart button is the
 * previous size's, and a spec tapped a phone's button on its way out until its 3 minutes ran out (rv-hub-292).
 */
export async function tillIsPhone(page: Page): Promise<boolean> {
  const till = shown(page).locator('[data-testid=pos-till]');
  await till.waitFor({ state: 'visible' });
  const settled = await page.waitForFunction(
    ({ el, media, narrowerThan }) => {
      const style = getComputedStyle(el);
      const width = el.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const phone = matchMedia(media).matches || width < narrowerThan;
      return el.classList.contains('pos-till--phone') === phone ? { phone } : null;
    },
    { el: await till.elementHandle(), ...TILL_PHONE },
    { timeout: 10_000 },
  );
  return ((await settled.jsonValue()) as { phone: boolean }).phone;
}

/** The check on screen: on a phone it is the drawer behind the cart button, which this opens (once the till has laid
 *  itself out for the window, and only if the drawer is not open already: open, it covers the button). Elsewhere the
 *  check is beside the catalogue and there is nothing to open. */
export async function openTillCart(page: Page): Promise<void> {
  if (!(await tillIsPhone(page))) return;
  const till = shown(page).locator('[data-testid=pos-till]');
  if (!(await till.evaluate((el) => el.classList.contains('pos-till--cart-open')))) {
    await till.locator('[data-testid=pos-cart-fab]').click();
  }
  await expect(till).toHaveClass(/pos-till--cart-open/);
}

/** The sizes where a notice of the till is read: the fleet's three and the lowest phone. */
const NOTICE_SIZES = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
  { label: '320x568', width: 320, height: 568 },
] as const;

/** One test per size of `NOTICE_SIZES`, each on a page of its own in `locale`, closed after it. */
export function eachNoticeSize(
  locale: string,
  run: (page: Page, context: BrowserContext, size: (typeof NOTICE_SIZES)[number]) => Promise<void>,
): void {
  for (const size of NOTICE_SIZES) {
    test(size.label, async ({ browser }) => {
      const context = await browser.newContext({ baseURL: A, locale, viewport: { width: size.width, height: size.height } });
      try {
        await run(await context.newPage(), context, size);
      } finally {
        await context.close();
      }
    });
  }
}

/** For a `beforeAll`: cash without a cash session (the drawer's lock is sale-cash-gate.spec.ts's) and a dish of the run
 *  to sell, `E2E <label> Dish <run>`, whose SKU is `E2E-<label>-<run>`. */
export async function dishForTheTill(browser: Browser, label: string, run: string): Promise<Product> {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await drawerOff(context);
  const dish = await createProduct(context, { name: `E2E ${label} Dish ${run}`, sku: `E2E-${label}-${run}`, price: 700, tax_category_key: 'restaurant.food' });
  await context.close();
  return dish;
}

/** A box on screen, in the window's pixels. */
export interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

/** Notices that last `ms` stay until the spec has read them, for a page not loaded yet: where a notice sits is the
 *  point, not how long it lasts, and read without this a check passes once the notice has gone by itself. No other
 *  timer changes. */
export async function holdNotices(page: Page, ms: number): Promise<void> {
  await page.addInitScript((noticeMs) => {
    const original = window.setTimeout.bind(window);
    window.setTimeout = ((run: TimerHandler, after?: number, ...rest: unknown[]) =>
      original(run, after === noticeMs ? 600_000 : after, ...rest)) as typeof window.setTimeout;
  }, ms);
}

/** The notice's own box: the host of an `ion-toast` fills the screen. */
export function noticeBox(notice: Locator): Promise<Box> {
  return notice.evaluate((el) => {
    const box = el.shadowRoot!.querySelector('.toast-wrapper')!.getBoundingClientRect();
    return { top: box.top, bottom: box.bottom, left: box.left, right: box.right };
  });
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

/** Whether two boxes on screen share any of their pixels. */
export const overlap = (a: Box, b: Box): boolean => a.top < b.bottom && a.bottom > b.top && a.left < b.right && a.right > b.left;

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
      // Their events, delivered or not: an event about a sale this deletes would reach Invoicing at the next relay
      // pass (a spec's, as the worker's), find no sale and, after its attempts, stay in System › Failed events (and
      // the bell) of the business for the specs that come next.
      `create temp table e2e_events as select id from live_outboxevent
        where payload->>'sale_id' in (select id::text from e2e_sales) or payload->>'order_id' in (select id::text from e2e_orders)`,
      'delete from base_eventdelivery where event_id in (select id from e2e_events)',
      'delete from live_outboxevent where id in (select id from e2e_events)',
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

/** Where the number and the date and time sit on `paper`: how many lines each takes, whether the date shares the
 *  number's line (after it) or starts right under it, and how far any of them runs past the paper's printable width. */
export interface NumberRow {
  numberLines: number;
  dateLines: number;
  dateBeside: boolean;
  dateUnder: boolean;
  overflow: number;
}

export async function numberRow(paper: Locator): Promise<NumberRow> {
  return paper.evaluate((el) => {
    const style = getComputedStyle(el);
    const right = el.getBoundingClientRect().right - parseFloat(style.paddingRight);
    const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
    /** The text boxes of `node`, one per piece of a line it wraps onto. */
    const boxes = (node: Element) => {
      const range = document.createRange();
      range.selectNodeContents(node);
      return [...range.getClientRects()].filter((box) => box.width > 0 && box.height > 0);
    };
    /** How many lines `node`'s text takes: its boxes grouped by their top, half a line apart. */
    const lines = (node: Element) => {
      const tops = boxes(node).map((box) => box.top).sort((a, b) => a - b);
      return tops.filter((top, index) => index === 0 || top - tops[index - 1] > lineHeight / 2).length;
    };
    const number = el.querySelector('[data-testid=sale-receipt-number]')!;
    const date = el.querySelector('[data-testid=sale-receipt-datetime]')!;
    const numberBoxes = boxes(number);
    const dateBoxes = boxes(date);
    const numberTop = Math.min(...numberBoxes.map((box) => box.top));
    const numberRight = Math.max(...numberBoxes.map((box) => box.right));
    const dateTop = Math.min(...dateBoxes.map((box) => box.top));
    const dateLeft = Math.min(...dateBoxes.map((box) => box.left));
    const dateRight = Math.max(...dateBoxes.map((box) => box.right));
    // How far the date's text is from the number's, against the height of a line. Both are set in the same font, so its
    // text box cancels out: between text boxes, a box is as tall as the machine's font says, and `ReceiptPaper.vue` asks
    // for a font the Hub does not serve (hub#731: 3.5 px of nothing on a Mac, with no blank line on the paper). The boxes
    // of the two flex items would not do either: they touch with padding inside them or a row that stretches them.
    const dateStyle = getComputedStyle(date);
    const dateFontSize = parseFloat(dateStyle.fontSize);
    const dateLineHeight = parseFloat(dateStyle.lineHeight) || dateFontSize * 1.2;
    const lineGap = dateTop - Math.max(...numberBoxes.map((box) => box.top)) - dateLineHeight;
    return {
      numberLines: lines(number),
      dateLines: lines(date),
      dateBeside: Math.abs(dateTop - numberTop) < lineHeight / 2 && dateLeft >= numberRight,
      // Right under it, as the next line of the paper: no blank line between them, not even inside a line twice the font.
      dateUnder: lineGap >= -1 && lineGap <= 2 && dateLineHeight < 2 * dateFontSize,
      // Whole pixels: text set flush right lands a hundredth of a pixel either side of the edge.
      overflow: Math.max(0, Math.round(Math.max(numberRight, dateRight) - right)),
    };
  });
}

// The four links of VeriFactu and of an invoice's receipt that leave the app (VERIFACTU-F12, F18, F19 and INVOICE-F17),
// in Chrome against the real Hub, Invoicing and VeriFactu:
//   - in the installed app, each one asks the system browser for its address and opens no tab of its own (a `_blank` in
//     the app's webview opens nothing, which was the bug);
//   - in a browser, each one opens its address in a new tab and asks nothing.
// Tauri does not run in Playwright: the installed app's bridge is simulated at the edge, as in `shell-nav.spec.ts`
// (`window.__TAURI__`, which records what it is asked). Whether the app takes the AEAT's address is for the native
// app's own tests. Nothing here reaches the AEAT: its test site is stubbed. The declaration lives on the stack's own
// SaaS.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shown } from './helpers';
import { cleanInvoices, ensureIssuer, issuedIds, snapshotSeries } from './invoice-helpers';
import { stamp } from './sale-helpers';

const RUN = stamp();
const OPEN_EXTERNAL_COMMAND = 'open_external_url';
/** The installed app lives on phones and tablets: its links are clicked at a phone's size, scrolled to as a finger would. */
const PHONE = { width: 375, height: 667 };

interface Ticket {
  id: string;
  invoiceId: string;
  number: string;
  qrUrl: string;
}

/** What the app was asked to open, from the page's bridge. */
type Bridge = { opened: string[] };

let ticket: Ticket;

/** From the next page load on, the page runs inside the installed app (after the login, which is the SaaS's page). */
async function insideTheApp(page: Page): Promise<void> {
  await page.addInitScript((command: string) => {
    const bridge: Bridge = { opened: [] };
    const win = window as unknown as { __TAURI__: unknown; __bridge: Bridge };
    win.__bridge = bridge;
    win.__TAURI__ = {
      core: {
        invoke: async (asked: string, args?: { url?: string }) => {
          if (asked === command) bridge.opened.push(args?.url ?? '');
          return null;
        },
        addPluginListener: async () => ({ unregister: async () => undefined }),
      },
    };
  }, OPEN_EXTERNAL_COMMAND);
}

const askedToOpen = (page: Page): Promise<string[]> => page.evaluate(() => (window as unknown as { __bridge: Bridge }).__bridge.opened);

/** The AEAT's test site, stubbed: the run never goes out to it. */
async function stubTheAeat(context: BrowserContext): Promise<void> {
  await context.route('https://prewww2.aeat.es/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>AEAT</title>' }),
  );
}

/** Where the declaration lives on this server: VeriFactu's own answer, as the page reads it. */
async function declarationUrl(context: BrowserContext): Promise<string> {
  const res = await api<{ declaration_url: string }>(context, A, 'GET', '/verifactu/config');
  expect(res.status, 'VeriFactu answers its configuration').toBe(200);
  return res.data.declaration_url;
}

/** One link: the page it lives on, how to find it there, and the address it goes to. */
interface ExternalLink {
  name: string;
  path: () => string;
  find: (page: Page) => Promise<Locator>;
  address: (context: BrowserContext) => Promise<string>;
}

const LINKS: ExternalLink[] = [
  {
    name: 'VERIFACTU-F18 «Verify at the AEAT» of a row in Records',
    path: () => '/verifactu/records',
    find: async (page) => {
      const list = shown(page);
      await list.locator('[data-testid=verifactu-records-search] input').fill(ticket.number);
      const row = list.locator('[data-testid=verifactu-records-row]').filter({ hasText: ticket.number });
      await expect(row).toHaveCount(1);
      return list.locator(`[data-testid=verifactu-records-row-${ticket.id}-verify]`);
    },
    address: async () => ticket.qrUrl,
  },
  {
    name: 'VERIFACTU-F18 «Verify at the AEAT» of a record',
    path: () => `/verifactu/records/${ticket.id}`,
    find: async (page) => shown(page).locator('[data-testid=verifactu-record-verify]'),
    address: async () => ticket.qrUrl,
  },
  {
    name: 'VERIFACTU-F12 «Read the signed declaration» of Settings',
    path: () => '/verifactu/settings',
    find: async (page) => shown(page).locator('[data-testid=verifactu-settings-declaration]'),
    address: declarationUrl,
  },
  {
    name: 'INVOICE-F17 «Check at the tax agency» of an invoice',
    path: () => `/invoice/invoices/${ticket.invoiceId}`,
    find: async (page) => shown(page).locator('[data-testid=invoice-verifactu-check]'),
    address: async () => ticket.qrUrl,
  },
];

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/verifactu/records');
  snapshotSeries();
  await ensureIssuer(context);
  const issued = await api<{ id: string; number: string }>(context, A, 'POST', '/invoice/invoices', {
    series_code: 'TICKET',
    lines: [{ description: `e2e VeriFactu external links ${RUN}`, quantity: '1', unit_price: 1000, tax_rate: '21' }],
  });
  expect(issued.status, 'Invoicing issues the ticket').toBe(201);
  issuedIds.add(issued.data.id);
  const sealed = await api<{ record: { id: string; qr_url: string } | null }>(context, A, 'GET', `/verifactu/records/by_invoice?invoice_id=${issued.data.id}`);
  expect(sealed.data.record, 'the ticket was sealed in VeriFactu').not.toBeNull();
  ticket = { id: sealed.data.record!.id, invoiceId: issued.data.id, number: issued.data.number, qrUrl: sealed.data.record!.qr_url };
  // Its record belongs to the AEAT's test environment: the address these tests click is never the real one.
  expect(new URL(ticket.qrUrl).hostname).toBe('prewww2.aeat.es');
  expect(psql(`select environment from verifactu_record where id = '${ticket.id}'`)).toBe('testing');
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

test.afterAll(() => {
  // The records go with their invoices (a record keeps its invoice).
  cleanInvoices();
});

for (const link of LINKS) {
  test(`${link.name}: in the installed app it asks the system browser and opens no tab`, async ({ page, context }) => {
    await stubTheAeat(context);
    await login(page, A, '/verifactu/records');
    const address = await link.address(context);
    await insideTheApp(page);
    await page.setViewportSize(PHONE);
    await page.goto(`${A}${link.path()}`);
    const target = await link.find(page);
    await expect(target).toBeVisible();

    const tabs: Page[] = [];
    context.on('page', (tab) => tabs.push(tab));
    const before = page.url();
    await target.click();

    await expect.poll(() => askedToOpen(page), { message: 'the system browser was asked for the link’s address' }).toEqual([address]);
    // A click the link let through has announced its tab by now.
    await page.waitForTimeout(500);
    expect(tabs.map((tab) => tab.url())).toEqual([]);
    expect(page.url()).toBe(before);
  });

  test(`${link.name}: in a browser it opens its address in a new tab`, async ({ page, context }) => {
    await stubTheAeat(context);
    await login(page, A, link.path());
    const address = await link.address(context);
    const target = await link.find(page);
    await expect(target).toBeVisible();

    // Any new page, not only a popup Playwright ties to this one: these links are `noopener`.
    const opened = context.waitForEvent('page');
    const before = page.url();
    await target.click();
    const tab = await opened;
    await tab.waitForURL(address);
    await tab.close();
    expect(page.url()).toBe(before);
  });
}

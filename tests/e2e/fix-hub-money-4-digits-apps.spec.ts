// flow: STAFF-F21, STAFF-F23, INVENTORY-F01, INVENTORY-F02, INVENTORY-F17 and the amounts of Cash register, Menus,
// Kitchen, Services and Tables (hub#494, hub#525, hub#653, hub#654, hub#655, hub#657, hub#658) — an amount of four
// digits (1.234,56 €) as the owner reads it in Spanish in the list of each of these seven apps says «1.234,56 €», its
// thousands grouped, never «1234,56 €» (Spanish CLDR only groups from five digits on; every other screen of the Hub
// groups from four), at 390, 834 and 1440.
// What this file creates is deleted after it, also when a test fails.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, stamp } from './sale-helpers';
import { cleanUp as cleanServices, named, post } from './service-helpers';

const KEY = 'FIX-HUB-MONEY-4-DIGITS-APPS';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const RUN = stamp();
const AMOUNT = 123456;
/** «1.234,56 €» as Intl paints it in Spanish (a no-break space before «€»). */
const GROUPED = /1\.234,56\s€/;
const UNGROUPED = /1234,56/;

const SKU = `E2E-MNA-${RUN}`;
const MEMBER = `MNA${RUN}`;
const MENU = `E2E MNA Menu ${RUN}`;
const TICKET_LABEL = `e2e mna ${RUN}`;
const ZONE = `E2E MNA ${RUN}`;
const SERVICE = named('Thousands');

const run = { member: '', menu: '', service: '', session: '', sessionNumber: '', ticket: '', check: '' };
let dish: Product;

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

/** One drawer open per business: a shift some earlier run left open is closed, at its expected. */
async function closeLeftOpen(context: BrowserContext): Promise<void> {
  const current = await api<{ session: { id: string; expected_balance: number | null } | null }>(context, A, 'GET', '/cash_register/sessions/current');
  const left = current.data.session;
  if (!left) return;
  const closed = await api(context, A, 'POST', '/cash_register/sessions/close', {
    session_id: left.id,
    closing_balance: Math.max(left.expected_balance ?? 0, 0),
    closing_notes: 'e2e: left open by an earlier run',
  });
  expect(closed.status).toBe(200);
}

/** Seats a check at a table of the run's own room with the dish on it and charges it by card, through Sales. */
async function chargedCheck(context: BrowserContext): Promise<string> {
  const zone = await post<{ id: string }>(context, '/table/zones', { name: ZONE });
  const table = await post<{ id: string }>(context, '/table/tables', { zone_id: zone.id, number: '1', capacity: 4 });
  const check = await post<{ id: string; order_id: string }>(context, '/table/sessions/open', { table_id: table.id, guests_count: 2 });
  const added = await api(context, A, 'POST', '/sale/orders/add_line', { order_id: check.order_id, product_id: dish.id, quantity: '1' });
  expect(added.status, JSON.stringify(added.data)).toBe(200);
  const sale = await chargeByApi(context, { order_id: check.order_id, payments: [{ method: 'card' }] });
  expect(sale.total).toBe(AMOUNT);
  return check.id;
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  try {
    await login(await context.newPage(), A, '/inventory/products');
    dish = await createProduct(context, { name: `E2E MNA ${RUN} Lobster`, sku: SKU, price: AMOUNT, tax_category_key: 'restaurant.food' });
    run.member = (await post<{ id: string }>(context, '/staff/members', { first_name: `${MEMBER} Ana`, last_name: 'Thousands', hourly_rate: AMOUNT })).id;
    run.menu = (await post<{ id: string }>(context, '/combo/combos', { name: MENU, price: AMOUNT, tax_category_key: 'restaurant.food' })).id;
    run.service = (await post<{ id: string }>(context, '/service/services', { name: SERVICE, price: AMOUNT, tax_category_key: 'service.generic' })).id;
    run.ticket = (await post<{ number: string }>(context, '/kitchen/tickets', { label: TICKET_LABEL, items: [{ product_id: dish.id, quantity: '1' }] })).number;
    run.check = await chargedCheck(context);
    await closeLeftOpen(context);
    const session = await post<{ id: string; number: string }>(context, '/cash_register/sessions/open', { opening_balance: AMOUNT });
    run.session = session.id;
    run.sessionNumber = session.number;
  } finally {
    await context.close();
  }
});

test.afterAll(() => {
  const tickets = `select id from kitchen_ticket where label like 'e2e mna %'`;
  const zones = `select id from table_zone where name like 'E2E MNA %'`;
  const tables = `select id from table_table where zone_id in (${zones})`;
  try {
    if (run.session) {
      psql(
        [
          `delete from cash_register_count where session_id = '${run.session}'`,
          `delete from cash_register_movement where session_id = '${run.session}'`,
          `delete from cash_register_session where id = '${run.session}'`,
        ].join('; '),
      );
    }
    psql(
      [
        `delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (${tickets}))`,
        `delete from kitchen_logentry where ticket_id in (${tickets})`,
        `delete from kitchen_ticketitem where ticket_id in (${tickets})`,
        `delete from kitchen_ticket where id in (${tickets})`,
        `delete from staff_member where first_name like 'MNA%'`,
        `delete from combo_combo where name like 'E2E MNA %'`,
        `delete from table_sessionmove where table_id in (${tables}) or session_id in (select id from table_tablesession where table_id in (${tables}))`,
        `update table_tablesession set transferred_from_id = null, merged_into_id = null, split_from_id = null where table_id in (${tables})`,
        `delete from table_tablesession where table_id in (${tables})`,
        `delete from table_table where id in (${tables})`,
        `delete from table_zone where id in (${zones})`,
      ].join('; '),
    );
    cleanServices();
  } finally {
    try {
      cleanSales();
    } finally {
      cleanInventory();
    }
  }
});

/** The owner on `a` in Spanish: the Hub's language cookie, as the sign-in sets it from the account. */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/inventory/products');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/inventory/products`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

async function groupedIn(row: Locator, where: string): Promise<void> {
  // A screen on a busy machine takes longer than an assertion's 10 s to load its list (as `actionTimeout` above).
  await expect(row, where).toBeVisible({ timeout: 30_000 });
  await expect(row, where).toContainText(GROUPED);
  await expect(row, where).not.toContainText(UNGROUPED);
}

/** The screens, each with the row that holds the run's amount. */
const SCREENS: { app: string; issue: string; path: string; row: (page: Page) => Promise<Locator> }[] = [
  {
    app: 'staff',
    issue: 'hub#494',
    path: '/staff/members',
    row: async (page) => {
      await shown(page).locator('[data-testid=staff-members-search] input').fill(MEMBER);
      return shown(page).locator(`[data-testid=staff-members-row][data-id="${run.member}"]`);
    },
  },
  {
    app: 'inventory',
    issue: 'hub#525',
    path: '/inventory/products',
    row: async (page) => {
      await shown(page).locator('[data-testid=inventory-products-search] input').fill(SKU);
      return shown(page).locator('[data-testid=inventory-products-row]', { hasText: SKU });
    },
  },
  {
    app: 'cash_register',
    issue: 'hub#653',
    path: '/cash_register/sessions',
    row: async (page) => shown(page).locator(`[data-testid=cash-register-sessions-row][data-id="${run.session}"]`),
  },
  {
    app: 'combo',
    issue: 'hub#654',
    path: '/combo/menus',
    row: async (page) => {
      await shown(page).locator('[data-testid=combo-menus-search] input').fill(RUN);
      return shown(page).locator(`[data-testid=combo-menus-row][data-id="${run.menu}"]`);
    },
  },
  {
    app: 'kitchen',
    issue: 'hub#655',
    path: '/kitchen/tickets',
    row: async (page) => {
      await shown(page).locator('[data-testid=kitchen-tickets-search] input').fill(TICKET_LABEL);
      return shown(page).locator('[data-testid=kitchen-tickets-row]').filter({ hasText: run.ticket }).first();
    },
  },
  {
    app: 'service',
    issue: 'hub#657',
    path: '/service/services',
    row: async (page) => {
      await shown(page).locator('[data-testid=service-services-search] input').fill(SERVICE);
      return shown(page).locator(`[data-testid=service-services-row][data-id="${run.service}"]`);
    },
  },
  {
    app: 'table',
    issue: 'hub#658',
    path: '/table/sessions',
    row: async (page) => {
      await shown(page).locator('[data-testid=table-sessions-segment-closed]').click();
      return shown(page).locator(`[data-testid=table-sessions-row][data-id="${run.check}"]`);
    },
  },
];

for (const size of SIZES) {
  test(`${KEY} at ${size.label}: the seven apps paint a four-digit amount with its thousands grouped`, async ({ browser }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      for (const screen of SCREENS) {
        await page.goto(`${A}${screen.path}`);
        await groupedIn(await screen.row(page), `${screen.issue} ${screen.app} at ${size.label}`);
        await capture(page, `${KEY}-${screen.app}-${size.label}`);
      }
    } finally {
      await context.close();
    }
  });
}

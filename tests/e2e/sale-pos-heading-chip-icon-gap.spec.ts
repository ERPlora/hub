// flow: SALE-F19, SALE-F16, SALE-F05 — the chips of the check's heading in the till keep their icon apart from their
// text, in Chrome on the real stack (Sales, Tables, Customers, Inventory). A check seated at the run's table with a
// customer shows the table, the customer and «Served by me»; a business that requires a customer shows «Customer
// required» on a new check. Measured at 375×667, 820×1180 and 1280×720, in English and in Spanish: Ionic's 8px between
// the icon and the text, the icon 8px from the chip's edge and whole inside it. What the run creates is deleted, and
// «Require a customer» goes back to what it was.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, record, shown } from './helpers';
import { cleanUp as cleanCustomers, createCard, e2eName, spanishMobile } from './customer-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { addToTill, checkAtEachSize, cleanSales, stamp, tillIn, tillReady, zoneWithTable } from './sale-helpers';
import { WINDOW_SIZES } from './screen';

const RUN = stamp();
const ZONE = `E2E ChipGap ${RUN}`;
const NUMBER = RUN;
const KEY = 'SALE-POS-HEADING-CHIP-ICON-GAP';

/** Ionic's margin between a chip's leading icon and its text, and its pull of the icon toward the chip's edge. */
const IONIC_GAP = 8;
const IONIC_PULL = 4;
/** Ionic's inline padding of `ion-chip`, which the shell keeps. */
const IONIC_INLINE = 12;

let coffee: Product;
let tableId: string;
let customer: { id: string; name: string };
let requiredBefore = false;

function cleanZone(): void {
  const zones = "select id from table_zone where name like 'E2E ChipGap %'";
  const tables = `select id from table_table where zone_id in (${zones})`;
  psql(
    [
      `create temp table e2e_chipgap_sessions as select id from table_tablesession where table_id in (${tables})`,
      'delete from table_sessionmove where session_id in (select id from e2e_chipgap_sessions)',
      `delete from table_hold where table_id in (${tables})`,
      'delete from table_tablesession where id in (select id from e2e_chipgap_sessions)',
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where id in (${zones})`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  cleanZone();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  requiredBefore = (await api<{ require_customer: boolean }>(context, A, 'GET', '/sale/settings')).data.require_customer;
  coffee = await createProduct(context, { name: `E2E Chip gap coffee ${RUN}`, sku: `E2E-CHIPGAP-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  ({ tableId } = await zoneWithTable(context, ZONE, NUMBER));
  const card = await createCard(context, { name: e2eName('Chip gap'), phone: spanishMobile() });
  customer = { id: card.id, name: card.name };
  await context.close();
});

test.afterAll(() => {
  cleanZone();
  cleanSales();
  cleanInventory();
  cleanCustomers();
});

interface ChipIcon {
  testid: string;
  marginEnd: string;
  /** From the icon's box to the first box of the text after it, in px. */
  gap: number;
  /** From the chip's start edge, inside its border, to the icon, in px. */
  inset: number;
  inside: boolean;
}

/** The leading icon of `chip` and the text after it, as laid out: the text is whatever follows the icon in the chip. */
function chipIcon(chip: Locator): Promise<ChipIcon> {
  return chip.evaluate((el) => {
    const icon = el.querySelector(':scope > ion-icon');
    if (!icon || el.firstElementChild !== icon) throw new Error(`no leading icon in ${el.outerHTML}`);
    const range = document.createRange();
    range.setStartAfter(icon);
    range.setEnd(el, el.childNodes.length);
    const text = [...range.getClientRects()].filter((r) => r.width > 0);
    if (!text.length) throw new Error(`no text after the icon in ${el.outerHTML}`);
    const box = el.getBoundingClientRect();
    const at = icon.getBoundingClientRect();
    return {
      testid: el.getAttribute('data-testid') ?? '',
      marginEnd: getComputedStyle(icon).marginInlineEnd,
      gap: Math.min(...text.map((r) => r.left)) - at.right,
      inset: at.left - box.left - parseFloat(getComputedStyle(el).borderLeftWidth),
      inside: at.width >= 1 && at.left >= box.left - 0.5 && at.right <= box.right + 0.5,
    };
  });
}

/** Each chip of `testids` in the check's heading, at each size (on a phone, in its drawer), captured and measured. */
async function measureChips(page: Page, lang: string, testids: string[]): Promise<void> {
  await checkAtEachSize(page, WINDOW_SIZES, async (label) => {
    const chips = testids.map((testid) => shown(page).locator(`[data-testid=${testid}]`).filter({ visible: true }));
    for (const chip of chips) await expect(chip).toBeVisible();
    await capture(page, `${KEY}-${testids[0]}-${lang}-${label}`);
    for (const chip of chips) {
      const measured = await chipIcon(chip);
      record(`${KEY}-${measured.testid}-${lang}-${label}`, measured);
      const detail = `${lang} ${label}: ${JSON.stringify(measured)}`;
      expect(measured.marginEnd, detail).toBe(`${IONIC_GAP}px`);
      expect(measured.gap, detail).toBeGreaterThanOrEqual(IONIC_GAP - 0.5);
      expect(Math.abs(measured.inset - (IONIC_INLINE - IONIC_PULL)), detail).toBeLessThanOrEqual(0.5);
      expect(measured.inside, detail).toBe(true);
    }
  });
}

/** The till's check seated at the run's table and given the run's customer, at a desk's size. */
async function seatedWithCustomer(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 720 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addToTill(page, coffee);
  const till = shown(page);
  await till.locator('[data-testid=pos-table-trigger]').click();
  const sheet = page.locator('ion-modal[data-testid=pos-table]');
  await sheet.locator('ion-searchbar input').fill(NUMBER);
  await sheet.locator(`[data-testid=pos-table-tile-${tableId}]`).click();
  await expect(sheet).toBeHidden();
  await till.locator('[data-testid=customer-search-trigger]').click();
  const search = page.locator('[data-testid=customer-search-modal]');
  await search.locator('[data-testid=customer-picker-search] input').fill(customer.name);
  await search.locator(`[data-testid=customer-picker-result-${customer.id}]`).click();
  await expect(till.locator('[data-testid=pos-customer-chip]')).toContainText(customer.name);
}

async function inLanguage(page: Page, context: BrowserContext, lang: string): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 720 });
  await tillIn(page, context, lang);
  await tillReady(page);
}

async function requireCustomer(context: BrowserContext, on: boolean): Promise<void> {
  const saved = await api<{ require_customer: boolean }>(context, A, 'POST', '/sale/settings', { require_customer: on });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  expect(saved.data.require_customer).toBe(on);
}

const SEATED = ['pos-table-chip', 'pos-customer-chip', 'pos-staff-chip'];

test('SALE-F19 and F16: the table, customer and «Served by» chips keep their icon apart from their text', async ({ page, context }) => {
  await seatedWithCustomer(page);
  // The session, for ui-clip-sweep.sh over this same page.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await measureChips(page, 'en', SEATED);
  await inLanguage(page, context, 'es');
  await expect(shown(page).locator('[data-testid=pos-table-chip]').filter({ visible: true })).toHaveText(`Mesa ${NUMBER}`);
  await measureChips(page, 'es', SEATED);
});

test('SALE-F05: «Customer required» keeps its icon apart from its text', async ({ page, context }) => {
  await login(page, A, '/sale/pos');
  await requireCustomer(context, true);
  try {
    for (const lang of ['es', 'en']) {
      await inLanguage(page, context, lang);
      await measureChips(page, lang, ['pos-needs-customer', 'pos-staff-chip']);
    }
  } finally {
    await requireCustomer(context, requiredBefore);
  }
});

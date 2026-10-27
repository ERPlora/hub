// flow: BASE-F84
// FIX-HUB-BASE-APPROVAL-KEYPAD-CUT-ON-TABLET-DESKTOP (base/WORKBOOK.md BASE-F84): «An approval is needed» shows its
// whole PIN pad, the four rows with the 0 and erase, without scrolling, at a phone, a low phone, a tablet and a desk
// (Square's and Toast's manager override: the dialog fits its pad), in Spanish, whose texts are the longest. Opened
// from a real app that asks for it: the cashier
// (employee@example.com, who may not void) voids a charged ticket in Sales, and the owner approves it on the cashier's
// device with a PIN that has a 0, after erasing a wrong digit; «Approved by <name>» and the ticket is voided. On a
// screen too short for the whole pad (a laptop's browser) the dialog stays on screen and its content scrolls. The
// owner's PIN exists only while this file runs, after the cashier has entered (a PIN in hub `a` turns every browser's
// way in into the PIN pad: base-access.spec.ts), and everything this file creates goes with it (`afterAll`).
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, OWNER, psql, shot, shown, untilStill } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, type SaleOut, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-BASE-APPROVAL-KEYPAD-CUT-ON-TABLET-DESKTOP';
const SKU = `E2E-BAPR-${stamp()}`;
/** The key the cut hid: the PIN has a 0. */
const OWNER_PIN = '2580';
/** A phone, a tablet and a desk (the SaaS panel's `VIEWPORTS`), and the low phone the fleet sweeps (an iPhone SE). */
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
  { label: '375', width: 375, height: 667 },
];
/** A desk shorter than the dialog with its whole pad (a laptop's browser with its bars). */
const SHORT = { label: 'short', width: 1280, height: 600 };
/** The ticket of the wrong PIN. */
const WRONG = 'wrong';

test.describe.configure({ mode: 'serial' });

let owner: { context: BrowserContext; page: Page };
let cashier: { context: BrowserContext; page: Page };
let started = '';
let ownerName = '';
const tickets = new Map<string, SaleOut>();

/**
 * The username of whoever is signed in on `context`. Not by email: a hub database kept from a stack whose SaaS was
 * created again holds an older account with the same email (a new SaaS, new users), and the email names both.
 */
async function usernameOf(context: BrowserContext): Promise<string> {
  const me = await api<{ user: { id: string } | null }>(context, A, 'GET', '/me');
  expect(me.status, 'GET /api/me').toBe(200);
  const id = me.data.user?.id ?? '';
  expect(id, 'the person signed in').not.toBe('');
  return psql(`SELECT username FROM auth_user WHERE id = '${id}'`);
}

/** Every account of `email` in this hub's database: the cleanup leaves none of them with what this file made. */
const accountsOf = (email: string): string => `SELECT username FROM auth_user WHERE email = '${email}'`;

/** The owner's approvals of a void spent since this file started. */
const spentVoids = (): number =>
  Number(
    psql(
      `SELECT count(*) FROM base_approval WHERE operation = 'sale.sale.void' AND used_at IS NOT NULL AND approved_by = '${ownerName}' AND created_at >= '${started}'`,
    ),
  );

/** No PIN of the owner's left behind, in any of their accounts: the business's way in stays erplora.com's. */
function forgetThePin(): void {
  psql(`UPDATE base_credential SET pin_hash = '', pin_set_at = NULL WHERE username IN (${accountsOf(OWNER.email)})`);
}

test.beforeAll(async ({ browser }) => {
  started = psql('SELECT now()::text');
  // Card charges issue tickets when the hub has an issuer, and a void its rectifying invoice: the cleanup gives
  // their numbers back.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  owner = { context, page: await context.newPage() };
  await login(owner.page, A, '/sale/sales');
  ownerName = await usernameOf(context);
  await drawerOff(context);
  await createProduct(context, { name: 'E2E Base approval', sku: SKU, price: 450, tax_category_key: 'product.generic' });
  for (const label of [...VIEWPORTS.map((viewport) => viewport.label), SHORT.label, WRONG]) {
    tickets.set(label, await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] }));
  }
  // The cashier enters while nobody of the business has a PIN: the way in is erplora.com's, as every spec's.
  const till = await browser.newContext({ baseURL: A });
  cashier = { context: till, page: await till.newPage() };
  await login(cashier.page, A, '/sale/sales', EMPLOYEE);
  // In Spanish (the Hub's language cookie, as the sign-in sets it): the longest texts above the pad.
  await till.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  // Only now the owner chooses a PIN («My profile»): who may approve, on the cashier's device.
  forgetThePin();
  const pin = await api<{ set: boolean }>(context, A, 'POST', '/me/pin', { pin: OWNER_PIN });
  expect(pin.status, JSON.stringify(pin.data)).toBe(200);
});

test.afterAll(async () => {
  forgetThePin();
  if (started) {
    psql(
      `DELETE FROM base_approval WHERE requested_by IN (${accountsOf(EMPLOYEE.email)}) AND operation = 'sale.sale.void' AND created_at >= '${started}'`,
    );
  }
  cleanSales();
  cleanInventory();
  restoreDrawer();
  // The cashier's session, for a sweep of what they see (as sale-approval.spec.ts saves it).
  if (process.env.E2E_SAVE_STORAGE_STATE) await cashier?.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await cashier?.context.close();
  await owner?.context.close();
});

const row = (page: Page, sale: SaleOut) => shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);

/** Sales, searched for `sale`'s number, with its row painted (a row on a desk, a card on a phone). */
async function find(page: Page, sale: SaleOut): Promise<void> {
  await page.goto(`${A}/sale/sales`);
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  await expect(row(page, sale)).toBeVisible();
}

/** «Void» on `sale`: its own button where the row has room, otherwise in its «⋮» menu. */
async function askToVoid(page: Page, sale: SaleOut): Promise<void> {
  const button = shown(page).locator(`[data-testid=sales-table-row-${sale.id}-void]`).first();
  if (!(await button.isVisible())) {
    await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-menu]`).first().click();
  }
  await page.locator(`[data-testid=sales-table-row-${sale.id}-void]`).filter({ visible: true }).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-void]');
  await expect(modal).toBeVisible();
  await modal.locator('[data-testid=sale-void-reason] textarea').fill('e2e approval pad');
  await modal.locator('[data-testid=sale-void-submit]').click();
}

/** «An approval is needed», over the window that asked. */
const approval = (page: Page) => page.locator('ion-modal').filter({ has: page.getByTestId('approval-action') });

/** The dialog open on `sale`'s void at `viewport`, on the owner's pad. */
async function openOnThePad(page: Page, sale: SaleOut, viewport: { width: number; height: number }): Promise<Locator> {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await find(page, sale);
  await askToVoid(page, sale);
  const dialog = approval(page);
  await expect(dialog.getByTestId('approval-action')).toHaveText(/^(Approving: Void a sale|Se aprueba: Anular una venta)$/);
  // The owner's face, when there is a choice; with one person the pad is already theirs.
  await expect(dialog.getByTestId('pinpad').or(dialog.getByTestId('pin-face').first())).toBeVisible();
  if (await dialog.getByTestId('pin-face').count()) {
    await dialog.getByTestId('pin-face').filter({ hasText: /owner/i }).first().click();
  }
  await expect(dialog.getByTestId('pinpad')).toBeVisible();
  await untilStill(page);
  return dialog;
}

/** The last row of the pad (the 0 and erase) lies inside the dialog's visible frame and the screen, unscrolled. */
async function expectWholePad(page: Page, dialog: Locator, label: string): Promise<void> {
  const frame = await dialog.locator('.modal-wrapper').boundingBox();
  const screen = page.viewportSize();
  expect(frame, `the dialog's frame at ${label}`).not.toBeNull();
  expect(screen).not.toBeNull();
  const bottom = Math.min(frame!.y + frame!.height, screen!.height);
  const right = Math.min(frame!.x + frame!.width, screen!.width);
  for (const id of ['pinpad-key-0', 'pinpad-erase', 'pinpad-key-1']) {
    const key = await dialog.getByTestId(id).boundingBox();
    expect(key, `${id} at ${label}`).not.toBeNull();
    expect(key!.y, `${id} below the dialog's top at ${label}`).toBeGreaterThanOrEqual(frame!.y);
    expect(key!.x, `${id} right of the dialog's left at ${label}`).toBeGreaterThanOrEqual(frame!.x);
    expect(key!.y + key!.height, `${id} above the dialog's visible bottom at ${label}`).toBeLessThanOrEqual(bottom + 0.5);
    expect(key!.x + key!.width, `${id} left of the dialog's visible right at ${label}`).toBeLessThanOrEqual(right + 0.5);
  }
}

const escaped = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

for (const viewport of VIEWPORTS) {
  test(`BASE-F84: the whole PIN pad is in view at ${viewport.label} and a manager approves with a PIN that has a 0`, async () => {
    const { page } = cashier;
    const sale = tickets.get(viewport.label)!;
    const spentBefore = spentVoids();
    const dialog = await openOnThePad(page, sale, viewport);
    await expectWholePad(page, dialog, `${viewport.width}x${viewport.height}`);
    await page.screenshot({ path: shot(`${KEY}-${viewport.label}`) });

    // Erase takes a wrong digit back, then the PIN with its 0.
    const filled = dialog.locator('[data-testid=pinpad-dot].is-filled');
    await dialog.getByTestId('pinpad-key-9').click();
    await expect(filled).toHaveCount(1);
    await dialog.getByTestId('pinpad-erase').click();
    await expect(filled).toHaveCount(0);
    const name = (await dialog.getByTestId('pin-door-chosen').locator('.pin-door__name').innerText()).trim();
    for (const digit of OWNER_PIN) await dialog.getByTestId(`pinpad-key-${digit}`).click();

    const approvedBy = new RegExp(`(Approved by|Aprobado por) ${escaped(name)}`);
    await expect(page.locator('ion-toast').filter({ hasText: approvedBy }).first()).toBeVisible();
    await expect(dialog).toBeHidden();
    await expect(page.locator('ion-modal[data-testid=sale-void]')).toBeHidden();
    await expect
      .poll(async () => (await api<{ status: string }>(owner.context, A, 'GET', `/sale/sales/detail?sale_id=${sale.id}`)).data.status)
      .toBe('voided');
    // Once: the approval is spent with the void (Employees › Approvals keeps who approved it).
    expect(spentVoids()).toBe(spentBefore + 1);
  });
}

test('BASE-F84: on a screen too short for the whole pad, the dialog stays on screen and its content scrolls to the 0', async () => {
  const { page } = cashier;
  const sale = tickets.get(SHORT.label)!;
  const dialog = await openOnThePad(page, sale, SHORT);
  const frame = (await dialog.locator('.modal-wrapper').boundingBox())!;
  expect(frame.y, 'the dialog\'s top on screen').toBeGreaterThanOrEqual(0);
  expect(frame.y + frame.height, 'the dialog\'s bottom on screen').toBeLessThanOrEqual(SHORT.height);
  // The wheel over the pad, as a person scrolls it, brings its last row in.
  const one = (await dialog.getByTestId('pinpad-key-1').boundingBox())!;
  await page.mouse.move(one.x + one.width / 2, one.y + one.height / 2);
  await page.mouse.wheel(0, 600);
  await expect
    .poll(async () => {
      const zero = await dialog.getByTestId('pinpad-key-0').boundingBox();
      return zero !== null && zero.y + zero.height <= frame.y + frame.height + 0.5;
    })
    .toBe(true);
  await dialog.getByTestId('approval-cancel').click();
  await expect(dialog).toBeHidden();
  const modal = page.locator('ion-modal[data-testid=sale-void]');
  await modal.locator('[data-testid=sale-void-cancel]').click();
  await expect(modal).toBeHidden();
});

test('BASE-F84: a wrong PIN says those details do not approve it, in the dialog, and the till stays where it was', async () => {
  // The Hub answers the wrong PIN with a 401 (`base.approval_refused`): the dialog says so, the page is not reloaded
  // (the SDK took every 401 for a session that ended, FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX).
  const { page } = cashier;
  const sale = tickets.get(WRONG)!;
  const spentBefore = spentVoids();
  const dialog = await openOnThePad(page, sale, VIEWPORTS[0]);
  // A mark on this page's window: a reload would take it away.
  await page.evaluate(() => Object.assign(window, { approvalE2ePage: 'same' }));
  const wrong = OWNER_PIN.split('').reverse().join('');
  for (const digit of wrong) await dialog.getByTestId(`pinpad-key-${digit}`).click();

  await expect(dialog.getByTestId('pinpad-error')).toHaveText(
    /^(Those details do not approve this\. Check the name and the PIN, and try again\.|Esos datos no aprueban esto\. Revisa el nombre y el PIN, y vuelve a intentarlo\.)$/,
  );
  expect(await page.evaluate(() => (window as { approvalE2ePage?: string }).approvalE2ePage), 'the page was reloaded').toBe('same');
  await expect(page.locator('ion-modal[data-testid=sale-void]')).toBeVisible();
  // The refusal on the pad at a phone, a tablet and a desk (one wrong attempt: each counts against the person), with
  // the whole pad still in view under it.
  for (const viewport of VIEWPORTS.slice(0, 3)) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await untilStill(page);
    await expect(dialog.getByTestId('pinpad-error')).toBeVisible();
    await expectWholePad(page, dialog, `${viewport.width}x${viewport.height} with the refusal`);
    await page.screenshot({ path: shot(`FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX-approval-refused-${viewport.label}`) });
  }
  expect(spentVoids()).toBe(spentBefore);
  expect((await api<{ status: string }>(owner.context, A, 'GET', `/sale/sales/detail?sale_id=${sale.id}`)).data.status).not.toBe('voided');

  await dialog.getByTestId('approval-cancel').click();
  await expect(dialog).toBeHidden();
  const modal = page.locator('ion-modal[data-testid=sale-void]');
  await modal.locator('[data-testid=sale-void-cancel]').click();
  await expect(modal).toBeHidden();
});

// flow: SALE-F30
// flow: SALE-F31
// FIX-SALE-VOID-REFUND-ASKS-NO-APPROVAL (apps/sale/WORKBOOK.md SALE-F30 and F31; base/WORKBOOK.md BASE-F84): the cashier
// (employee@example.com, who may neither void nor refund) sees «Void» and «Refund» in Sales; confirming either opens
// «An approval is needed» over the window, the owner approves it with their PIN on the cashier's own device and it is
// done once, as the server then says; «Cancel» leaves the refusal inside the window, which stays open, and nothing is
// voided. Screenshots of the dialog over Sales in the three viewports. The owner's PIN exists only while this file
// runs, after the cashier has entered (a PIN in hub `a` turns every browser's way in into the PIN pad:
// base-access.spec.ts), and the approvals it records go with it, as everything else this file creates (`afterAll`).
// FIX-HUB-SALE-APPROVAL-E2E-REUSED-DB: the owner and the cashier are told by their session, not by their email (a hub
// database kept from a stack whose SaaS was created again holds an older account with each email), and the PIN and
// the approvals of every account of those emails go before and after, so a run that failed leaves the next one clean.
// FIX-HUB-SALE-OWN-COPY-OF-APPROVED-COMMAND-CONSEQUENCES (SALE-F30, F32; BASE-F84): what the approved void asks of other
// apps goes with it by the platform's rule: a sale paid with Lucía's voucher and a shampoo by card, voided by the
// cashier with the owner's PIN, gives its session back to the voucher and its rectifying invoice is issued in the void
// (the cashier may do neither on their own). Screenshots of that approval in the three viewports.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, OWNER, psql, shot, shown, untilStill } from './helpers';
import { cleanUp as cleanCustomers, createCard, e2eName } from './customer-helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { ensureIssuer, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, type SaleOut, stamp } from './sale-helpers';
import { cleanUp as cleanServices, named, post } from './service-helpers';

const KEY = 'FIX-SALE-VOID-REFUND-ASKS-NO-APPROVAL';
const VOUCHER_KEY = 'FIX-HUB-SALE-OWN-COPY-OF-APPROVED-COMMAND-CONSEQUENCES';
const SKU = `E2E-APR-${stamp()}`;
const OWNER_PIN = '2468';
/** The dialog over Sales at a phone, a tablet and a desk (the SaaS panel's `VIEWPORTS`). */
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

test.describe.configure({ mode: 'serial' });

let owner: { context: BrowserContext; page: Page };
let cashier: { context: BrowserContext; page: Page };
let toVoid: SaleOut;
let toRefund: SaleOut;
let toKeep: SaleOut;
let ownerName = '';
let cashierName = '';

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

/**
 * No PIN of the owner's left behind, in any of their accounts (the business's way in stays erplora.com's), and no
 * approval of a Sales action the cashier asked for, in any of theirs.
 */
function forgetThePinAndTheApprovals(): void {
  psql(`UPDATE base_credential SET pin_hash = '', pin_set_at = NULL WHERE username IN (${accountsOf(OWNER.email)})`);
  psql(`DELETE FROM base_approval WHERE requested_by IN (${accountsOf(EMPLOYEE.email)}) AND operation LIKE 'sale.%'`);
}

test.beforeAll(async ({ browser }) => {
  // What a run that failed left: with the owner's PIN still set, the way in to hub `a` asks for a PIN and the logins
  // below never reach Sales (the cashier's lands on `/pin/setup`).
  forgetThePinAndTheApprovals();
  // Card charges issue tickets when the hub has an issuer, and a void its rectifying invoice: the cleanup gives
  // their numbers back.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  owner = { context, page: await context.newPage() };
  await login(owner.page, A, '/sale/sales');
  ownerName = await usernameOf(context);
  await drawerOff(context);
  await createProduct(context, { name: 'E2E Approval', sku: SKU, price: 450, tax_category_key: 'product.generic' });
  toVoid = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  toRefund = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  toKeep = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  // The cashier enters while nobody of the business has a PIN: the way in is erplora.com's, as every spec's.
  const till = await browser.newContext({ baseURL: A });
  cashier = { context: till, page: await till.newPage() };
  await login(cashier.page, A, '/sale/sales', EMPLOYEE);
  cashierName = await usernameOf(till);
  // Only now the owner chooses a PIN («My profile»): who may approve, on the cashier's device.
  const pin = await api<{ set: boolean }>(context, A, 'POST', '/me/pin', { pin: OWNER_PIN });
  expect(pin.status, JSON.stringify(pin.data)).toBe(200);
});

test.afterAll(async () => {
  forgetThePinAndTheApprovals();
  cleanSales();
  cleanServices();
  cleanCustomers();
  cleanInventory();
  restoreDrawer();
  // The cashier's session, for a sweep of what they see (as base-employees.spec.ts saves the owner's).
  if (process.env.E2E_SAVE_STORAGE_STATE) await cashier?.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await cashier?.context.close();
  await owner?.context.close();
});

const row = (page: Page, sale: SaleOut) => shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);

/** Sales, searched for `sale`'s number, with its row painted. */
async function find(page: Page, sale: SaleOut): Promise<void> {
  await page.goto(`${A}/sale/sales`);
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  await expect(row(page, sale)).toBeVisible();
}

/** «An approval is needed», over the window that asked. */
const approval = (page: Page) => page.locator('ion-modal').filter({ has: page.getByTestId('approval-action') });

/** The owner approves on the cashier's device: their face (when there is a choice) and their PIN. */
async function ownerApproves(page: Page): Promise<void> {
  const dialog = approval(page);
  const faces = dialog.getByTestId('pin-face');
  if (await faces.count()) await faces.first().click();
  for (const digit of OWNER_PIN) await dialog.getByTestId(`pinpad-key-${digit}`).click();
}

interface Detail {
  status: string;
  voided_by: string;
  void_reason: string;
  void_invoice_status: string;
}

async function detail(sale: SaleOut): Promise<Detail> {
  return (await api<Detail>(owner.context, A, 'GET', `/sale/sales/detail?sale_id=${sale.id}`)).data;
}

/** The cashier asks to void `sale` from Sales with `reason`: «An approval is needed» opens over the window. */
async function askToVoid(page: Page, sale: SaleOut, reason: string) {
  await find(page, sale);
  await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-void]`).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-void]');
  await expect(modal).toBeVisible();
  await modal.locator('[data-testid=sale-void-reason] textarea').fill(reason);
  await modal.locator('[data-testid=sale-void-submit]').click();
  return { modal, dialog: approval(page) };
}

/** Lucía's sale: a haircut paid with a session of her voucher and the shampoo by card, charged with its ticket. */
async function paidWithAVoucher(context: BrowserContext): Promise<SaleOut> {
  await ensureIssuer(context);
  const haircut = await post<{ id: string }>(context, '/service/services', { name: named('Corte aprobado'), price: 2500, tax_category_key: 'service.generic' });
  const lucia = await createCard(context, { name: e2eName('Lucía') });
  const voucher = await post<{ id: string }>(context, '/service/packages', { name: named('Bono aprobado'), max_uses: 2, items: [{ service_id: haircut.id }] });
  const grant = await post<{ id: string }>(context, '/service/grants', { package_id: voucher.id, customer_id: lucia.id, amount: 9000 });
  const opened = await post<{ id: string; lines: { id: string; service_id: string | null }[] }>(context, '/sale/orders', {
    lines: [{ product: SKU }],
    service_lines: [{ service_id: haircut.id }],
  });
  const cut = opened.lines.find((line) => line.service_id === haircut.id);
  expect(cut, 'the haircut on the check').toBeDefined();
  await post(context, '/sale/orders/apply_voucher', { order_id: opened.id, line_id: cut?.id, grant_id: grant.id }, 200);
  return chargeByApi(context, { order_id: opened.id, customer_id: lucia.id, payments: [{ method: 'card' }] });
}

/** The status of the voucher session that paid a line of `sale`, in Services. */
const sessionOf = (sale: SaleOut): string =>
  psql(`SELECT status FROM service_redemption WHERE id = (SELECT voucher_session_id FROM sale_saleline WHERE sale_id = '${sale.id}' AND voucher_session_id IS NOT NULL)`);

test('SALE-F30: the cashier voids a charged ticket and the owner approves it with their PIN', async () => {
  const { page } = cashier;
  await find(page, toVoid);
  await shown(page).locator(`[data-testid=sales-table-row-${toVoid.id}-void]`).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-void]');
  await expect(modal).toBeVisible();
  await modal.locator('[data-testid=sale-void-reason] textarea').fill('e2e wrong ticket');
  await modal.locator('[data-testid=sale-void-submit]').click();

  const dialog = approval(page);
  await expect(dialog.getByTestId('approval-action')).toHaveText(/^(Approving: Void a sale|Se aprueba: Anular una venta)$/);
  await expect(dialog.getByTestId('pinpad').or(dialog.getByTestId('pin-face').first())).toBeVisible();
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });

  await ownerApproves(page);
  await expect(dialog).toBeHidden();
  await expect(modal).toBeHidden();
  await expect(page.locator('ion-toast').filter({ hasText: /Sale voided|Venta anulada/ }).first()).toBeVisible();
  await expect(row(page, toVoid)).toContainText(/Voided|Anulada/);
  const stored = await detail(toVoid);
  expect([stored.status, stored.void_reason, stored.voided_by]).toEqual(['voided', 'e2e wrong ticket', cashierName]);
  // Once: the approval is spent with the void, and Employees › Approvals keeps who approved it.
  expect(psql(`SELECT count(*) FROM base_approval WHERE operation = 'sale.sale.void' AND used_at IS NOT NULL AND approved_by = '${ownerName}' AND requested_by = '${cashierName}'`)).toBe('1');
});

test('SALE-F31: the cashier refunds a charged ticket and the owner approves it with their PIN', async () => {
  const { page } = cashier;
  await find(page, toRefund);
  await shown(page).locator(`[data-testid=sales-table-row-${toRefund.id}-refund]`).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-refund]');
  await expect(modal).toBeVisible();
  await expect(modal.locator(`[data-testid=refund-tender-${toRefund.payments[0].id}]`)).toBeVisible();
  await modal.locator('[data-testid=refund-propose-all]').click();
  await modal.locator('[data-testid=refund-reason] textarea, [data-testid=refund-reason] input').first().fill('e2e returned');
  await modal.locator('[data-testid=refund-confirm]').click();

  const dialog = approval(page);
  await expect(dialog.getByTestId('approval-action')).toHaveText(/^(Approving: Refund a sale|Se aprueba: Devolver una venta)$/);
  await ownerApproves(page);
  await expect(dialog).toBeHidden();
  await expect(modal).toBeHidden();
  await expect(page.locator('ion-toast').filter({ hasText: /Refund recorded\.|Devolución registrada\./ }).first()).toBeVisible();
  await expect.poll(async () => (await detail(toRefund)).status).toBe('refunded');
  await expect(row(page, toRefund)).toContainText(/Refunded|Devuelta/);
});

test('SALE-F30: «Cancel» on the approval leaves its refusal inside the window, and nothing is voided', async () => {
  const { page } = cashier;
  await find(page, toKeep);
  await shown(page).locator(`[data-testid=sales-table-row-${toKeep.id}-void]`).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-void]');
  await expect(modal).toBeVisible();
  await modal.locator('[data-testid=sale-void-reason] textarea').fill('e2e not approved');
  await modal.locator('[data-testid=sale-void-submit]').click();

  const dialog = approval(page);
  await expect(dialog.getByTestId('approval-action')).toBeVisible();
  await dialog.getByTestId('approval-cancel').click();
  await expect(dialog).toBeHidden();
  await expect(modal).toBeVisible();
  await expect(modal.getByTestId('sale-void-error')).toContainText(/This needs a manager.s approval\.|Esto necesita la aprobación de un encargado\./);
  expect((await detail(toKeep)).status).toBe('completed');
  await modal.locator('[data-testid=sale-void-cancel]').click();
  await expect(modal).toBeHidden();
});

test('SALE-F30, SALE-F32: an approved void of a sale paid with a voucher gives the session back and issues its rectifying invoice', async () => {
  const sale = await paidWithAVoucher(owner.context);
  expect(sessionOf(sale)).toBe('consumed');
  const { page } = cashier;
  const { modal, dialog } = await askToVoid(page, sale, 'e2e wrong customer');
  await expect(dialog.getByTestId('approval-action')).toHaveText(/^(Approving: Void a sale|Se aprueba: Anular una venta)$/);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await untilStill(page);
    await page.screenshot({ path: shot(`${VOUCHER_KEY}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });

  await ownerApproves(page);
  await expect(dialog).toBeHidden();
  await expect(modal).toBeHidden();
  await expect(row(page, sale)).toContainText(/Voided|Anulada/);
  // What the cashier may not do on their own went with the approved void, once.
  const stored = await detail(sale);
  expect([stored.status, stored.voided_by, stored.void_invoice_status]).toEqual(['voided', cashierName, 'issued']);
  expect(sessionOf(sale)).toBe('returned');
});

// flow: SALE-F30
// flow: SALE-F31
// flow: BASE-F84
// A cashier without voids (apps/sale/WORKBOOK.md SALE-F30 and F31; base/WORKBOOK.md BASE-F84): the owner gives the
// employee a role of the business that says no to voids and leaves refunds to approval. «Void» is refused before it
// begins, with no window and no PIN, and the hub refuses it too; «Refund» says a manager will have to approve it and the
// owner approves it with their PIN. The role changes with the screen open and the till follows it without a reload: with
// approval, the window opens and asks; back to no, the window already open is refused and asks nobody. Screenshots of
// both notices in the three viewports.
import { expect, type Page, test } from '@playwright/test';

import { approvalDialog, forgetThePinAndTheApprovals, ownerApproves, ownerChoosesPin, type Side } from './approval-helpers';
import { usernameOf } from './business';
import { A, api, capture, EMPLOYEE, psql, THREE_SIZES, uniqueName, usernamesOf } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { findSale, leaveTheTill, ownerAtSales, refundAll, saleRow } from './sale-approval-helpers';
import { cashiersTill, chargeByApi, cleanSales, restoreDrawer, type SaleOut, stamp } from './sale-helpers';
import { rowAction } from './service-helpers';
import { toastSaying } from './toast-helpers';
import { discardChanges } from './unsaved-back-helpers';

const SKU = `E2E-STA-${stamp()}`;
const NO_VOID = /Your role does not let you void a sale|Tu rol no permite anular una venta/;
const VOID_WITH_APPROVAL = /A manager will have to approve this void|Un encargado tendrá que aprobar esta anulación/;
const REFUND_WITH_APPROVAL = /A manager will have to approve this refund|Un encargado tendrá que aprobar esta devolución/;

test.describe.configure({ mode: 'serial' });

let owner: Side | undefined;
let cashier: Side | undefined;
let role = '';
let person = '';
let toVoid: SaleOut;
let toRefund: SaleOut;

const opened = <T>(side: T | undefined): T => {
  if (!side) throw new Error('beforeAll did not open this side.');
  return side;
};

async function ownerPosts<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const answer = await api<T>(opened(owner).context, A, 'POST', path, body);
  expect(answer.status, `${path} ${JSON.stringify(answer.data)}`).toBe(200);
  return answer.data;
}

const give = (key: string) => ownerPosts('/roles/assign', { person, role: key });
const says = (state: 'on' | 'approval' | 'off') => ownerPosts('/roles/update', { role, states: { 'sale.void_sale': state } });
const statusOf = async (sale: SaleOut): Promise<string> =>
  (await api<{ status: string }>(opened(owner).context, A, 'GET', `/sale/sales/detail?sale_id=${sale.id}`)).data.status;
const voidWindow = (page: Page) => page.locator('ion-modal[data-testid=sale-void]');

test.beforeAll(async ({ browser }) => {
  forgetThePinAndTheApprovals('sale');
  owner = await ownerAtSales(browser);
  await createProduct(owner.context, { name: 'E2E Approval states', sku: SKU, price: 450, tax_category_key: 'product.generic' });
  role = (await ownerPosts<{ key: string }>('/roles', { based_on: 'hub_employee', name: uniqueName('Cashier without voids') })).key;
  await ownerPosts('/roles/update', { role, states: { 'sale.void_sale': 'off', 'sale.refund_sale': 'approval' } });
  cashier = await cashiersTill(browser);
  person = await usernameOf(cashier.context);
  const till = cashier.context;
  toVoid = await chargeByApi(till, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  toRefund = await chargeByApi(till, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  await give(role);
  await ownerChoosesPin(owner.context);
});

test.afterAll(async () => {
  if (owner && person) await give('hub_employee');
  if (owner && role) await ownerPosts('/roles/delete', { role });
  forgetThePinAndTheApprovals('sale');
  cleanSales();
  cleanInventory();
  restoreDrawer();
  await leaveTheTill(cashier, owner);
});

test('SALE-F30: the role says no to voids: the till tells it before it begins, and the hub refuses it with nobody asked', async () => {
  const { page, context } = opened(cashier);
  await findSale(page, toVoid);
  for (const size of THREE_SIZES) {
    await page.setViewportSize(size);
    await rowAction(page, 'sales-table', toVoid.id, 'void');
    await expect(toastSaying(page, NO_VOID)).toBeVisible();
    await expect(voidWindow(page)).toBeHidden();
    await capture(page, `sale-approval-states-no-${size.label}`);
  }
  await page.setViewportSize({ width: 1280, height: 860 });

  const answer = await api<{ error: { code: string; approval?: unknown } }>(context, A, 'POST', '/sale/sales/void', {
    sale_id: toVoid.id,
    reason: 'e2e not mine to void',
  });
  expect([answer.status, answer.data.error.code, answer.data.error.approval]).toEqual([403, 'permission_denied', undefined]);
  expect(await statusOf(toVoid)).toBe('completed');
});

test('SALE-F31: the role refunds with approval: the till says so as it begins, and the owner approves it', async () => {
  const { page } = opened(cashier);
  await findSale(page, toRefund);
  const modal = page.locator('ion-modal[data-testid=sale-refund]');
  for (const size of THREE_SIZES) {
    await page.setViewportSize(size);
    await rowAction(page, 'sales-table', toRefund.id, 'refund');
    await expect(toastSaying(page, REFUND_WITH_APPROVAL)).toBeVisible();
    await expect(modal.locator('[data-testid=refund-propose-all]')).toBeVisible();
    await capture(page, `sale-approval-states-approval-${size.label}`);
    if (size.label === THREE_SIZES[THREE_SIZES.length - 1].label) break;
    await modal.locator('[data-testid=sale-refund-close]').click();
    await expect(modal).toBeHidden();
  }
  await refundAll(page, toRefund);
  await expect(approvalDialog(page).getByTestId('approval-action')).toHaveText(/^(Approving: Refund a sale|Se aprueba: Devolver una venta)$/);
  await ownerApproves(page);
  await expect(modal).toBeHidden();
  await expect.poll(() => statusOf(toRefund)).toBe('refunded');
  await expect(saleRow(page, toRefund)).toContainText(/Refunded|Devuelta/);
});

test('BASE-F84: the till follows the role with the screen open, and an open window is refused once it says no', async () => {
  const { page } = opened(cashier);
  await page.setViewportSize({ width: 1280, height: 860 });
  await findSale(page, toVoid);
  await page.evaluate(() => Object.assign(window, { e2eStillHere: true }));

  await says('approval');
  await expect(async () => {
    await rowAction(page, 'sales-table', toVoid.id, 'void');
    await expect(voidWindow(page)).toBeVisible({ timeout: 2000 });
  }).toPass();
  await expect(toastSaying(page, VOID_WITH_APPROVAL)).toBeVisible();
  await voidWindow(page).locator('[data-testid=sale-void-reason] textarea').fill('e2e role changed');

  await says('off');
  await voidWindow(page).locator('[data-testid=sale-void-submit]').click();
  await expect(voidWindow(page).getByTestId('sale-void-error')).toBeVisible();
  await expect(approvalDialog(page)).toHaveCount(0);
  expect(await statusOf(toVoid)).toBe('completed');
  expect(psql(`SELECT count(*) FROM base_approval WHERE requested_by IN (${usernamesOf(EMPLOYEE.email)}) AND operation = 'sale.sale.void'`)).toBe('0');

  await voidWindow(page).locator('[data-testid=sale-void-cancel]').click();
  await discardChanges(page);
  await expect(voidWindow(page)).toBeHidden();
  expect(await page.evaluate(() => (window as { e2eStillHere?: boolean }).e2eStillHere)).toBe(true);
});

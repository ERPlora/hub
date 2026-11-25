// Shared steps of the specs where the cashier of Sales needs a manager (BASE-F84, SALE-F30, SALE-F31): a sale found in
// Sales, «An approval is needed» and the owner approving with their PIN on the cashier's own device. The owner's PIN
// exists only while a file runs, after the cashier has entered (a PIN in hub `a` turns every browser's way in into the
// PIN pad: base-access.spec.ts), and it goes with the approvals it recorded, before and after. The owner and the cashier
// are told by their session, not by their email (a hub database kept from a stack whose SaaS was created again holds an
// older account with each email): the PIN and the approvals of every account of those emails go.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, EMPLOYEE, OWNER, psql, shown, usernamesOf } from './helpers';
import type { SaleOut } from './sale-helpers';

export const OWNER_PIN = '2468';

/**
 * No PIN of the owner's left behind, in any of their accounts (the business's way in stays erplora.com's), and no
 * approval of a Sales action the cashier asked for, in any of theirs.
 */
export function forgetThePinAndTheApprovals(): void {
  psql(`UPDATE base_credential SET pin_hash = '', pin_set_at = NULL WHERE username IN (${usernamesOf(OWNER.email)})`);
  psql(`DELETE FROM base_approval WHERE requested_by IN (${usernamesOf(EMPLOYEE.email)}) AND operation LIKE 'sale.%'`);
}

/** The owner chooses a PIN («My profile»): who may approve, on the cashier's device. */
export async function ownerChoosesPin(owner: BrowserContext): Promise<void> {
  const pin = await api<{ set: boolean }>(owner, A, 'POST', '/me/pin', { pin: OWNER_PIN });
  expect(pin.status, JSON.stringify(pin.data)).toBe(200);
}

export const saleRow = (page: Page, sale: SaleOut): Locator => shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);

/** Sales, searched for `sale`'s number, with its row painted. */
export async function findSale(page: Page, sale: SaleOut): Promise<void> {
  await page.goto(`${A}/sale/sales`);
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  await expect(saleRow(page, sale)).toBeVisible();
}

/** «An approval is needed», over the window that asked. */
export const approvalDialog = (page: Page): Locator => page.locator('ion-modal').filter({ has: page.getByTestId('approval-action') });

/** The owner approves on the cashier's device: their face (when there is a choice) and their PIN. */
export async function ownerApproves(page: Page): Promise<void> {
  const dialog = approvalDialog(page);
  const faces = dialog.getByTestId('pin-face');
  if (await faces.count()) await faces.first().click();
  for (const digit of OWNER_PIN) await dialog.getByTestId(`pinpad-key-${digit}`).click();
}

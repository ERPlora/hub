// Shared steps of the specs where the cashier of Sales needs a manager (SALE-F30, SALE-F31), over approval-helpers.ts: the
// owner in Sales, a sale found there, its whole refund filled in and the cashier leaving.
import { type Browser, expect, type Locator, type Page } from '@playwright/test';

import type { Side } from './approval-helpers';
import { usernameOf } from './business';
import { A, hostPage, shown } from './helpers';
import { snapshotSeries } from './invoice-helpers';
import { drawerOff, type SaleOut } from './sale-helpers';

/** The owner in Sales, by their username, with the cash drawer off for the run and the numbers of the tickets the card
 *  charges issue, and of the rectifying invoices of their voids, kept for the cleanup to give back. */
export async function ownerAtSales(browser: Browser): Promise<Side & { name: string }> {
  snapshotSeries();
  const owner = await hostPage(browser, A, { next: '/sale/sales' });
  const name = await usernameOf(owner.context);
  await drawerOff(owner.context);
  return { ...owner, name };
}

export const saleRow = (page: Page, sale: SaleOut): Locator => shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);

/** Sales, searched for `sale`'s number, with its row painted. */
export async function findSale(page: Page, sale: SaleOut): Promise<void> {
  await page.goto(`${A}/sale/sales`);
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  await expect(saleRow(page, sale)).toBeVisible();
}

/** The refund window, open on `sale`, asked to give it all back. */
export async function refundAll(page: Page, sale: SaleOut): Promise<Locator> {
  const modal = page.locator('ion-modal[data-testid=sale-refund]');
  await expect(modal).toBeVisible();
  await expect(modal.locator(`[data-testid=refund-tender-${sale.payments[0].id}]`)).toBeVisible();
  await modal.locator('[data-testid=refund-propose-all]').click();
  await modal.locator('[data-testid=refund-reason] textarea, [data-testid=refund-reason] input').first().fill('e2e returned');
  await modal.locator('[data-testid=refund-confirm]').click();
  return modal;
}

/** Both leave; the cashier's session is kept for a sweep of what they see when the run asks for it. */
export async function leaveTheTill(cashier: Side | undefined, owner: Side | undefined): Promise<void> {
  if (process.env.E2E_SAVE_STORAGE_STATE) await cashier?.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await cashier?.context.close();
  await owner?.context.close();
}

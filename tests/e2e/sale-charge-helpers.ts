import { expect, type Locator, type Page } from '@playwright/test';

import { shown } from './helpers';

/** On the till with a check on screen: «Charge», paid with `card` (the id of the business's card method) and confirmed;
 *  with `total`, the checkout shows it first. Returns the ticket, which opens on its own once the check is charged. */
export async function chargeByCard(page: Page, card: string, total?: RegExp): Promise<Locator> {
  await shown(page).locator('[data-testid=pos-charge]').click();
  const checkout = page.locator('[data-testid=sale-checkout-modal]');
  if (total) await expect(checkout.locator('[data-testid=sale-checkout-total]')).toContainText(total);
  await checkout.locator(`[data-testid=sale-checkout-method-${card}]`).click();
  await checkout.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(checkout).toBeHidden();
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  return receipt;
}

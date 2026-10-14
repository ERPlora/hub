// The till's customer search (CustomerSearch, CUSTOMER-F17, F18) in Ioan's Chrome, on its preview page
// (dev server only) until the Sales app mounts it: «Assign customer» opens the search; a pick hands
// the sale a copy of the card's tax details; «+ New customer «…»» creates one with name and phone and
// assigns it; a phone that is already a live card's is shown and asked about (use it or create a new
// one), never assigned in silence; «Remove customer» clears it.
import { expect, test } from '@playwright/test';

import { cleanUp, createCard, e2eName, inputOf, spanishMobile } from './customer-helpers';
import { A, login, shot, shown } from './helpers';

test.afterAll(() => cleanUp());

test('assign a customer, create one from the search, pick the card that has the phone, remove it', async ({ page, context }) => {
  await login(page, A, '/customer/preview/customer-search');
  const phone = spanishMobile();
  const card = await createCard(context, { name: e2eName('Till Ana'), phone, tax_id: '12345678Z', address: 'Calle Mayor 1', city: 'Madrid', postal_code: '28001', country: 'ES' });
  const preview = shown(page);
  await expect(preview.locator('[data-testid=customer-preview-none]')).toBeVisible();

  // Assign by searching the name.
  await preview.locator('[data-testid=customer-search-trigger]').click();
  const modal = page.locator('ion-modal[data-testid=customer-search-modal]');
  await expect(modal).toBeVisible();
  await modal.locator('[data-testid=customer-picker-search] input').fill(card.name);
  await modal.locator(`[data-testid=customer-picker-result-${card.id}]`).click();
  await expect(modal).toBeHidden();
  const snapshot = preview.locator('[data-testid=customer-preview-snapshot]');
  await expect(snapshot).toContainText(card.name);
  await expect(snapshot).toContainText('12345678Z');
  await expect(snapshot).toContainText(/Calle Mayor 1, 28001 Madrid, (Spain|España)/);
  await expect(preview.locator('[data-testid=customer-search-trigger]')).toHaveText(card.name);
  await page.screenshot({ path: shot('customer-search-assigned') });

  // «+ New customer «…»»: what was typed goes to «Name»; with a phone, created and assigned.
  const newName = e2eName('Till Marta');
  await preview.locator('[data-testid=customer-search-trigger]').click();
  await modal.locator('[data-testid=customer-picker-search] input').fill(newName);
  await expect(modal.locator('[data-testid=customer-picker-empty]')).toBeVisible();
  await modal.locator('[data-testid=customer-search-quick-add]').click();
  await expect(inputOf(modal, 'customer-search-quick-name')).toHaveValue(newName);
  await inputOf(modal, 'customer-search-quick-phone').fill(spanishMobile());
  await page.screenshot({ path: shot('customer-search-quick-add') });
  await modal.locator('[data-testid=customer-search-quick-submit]').click();
  await expect(modal).toBeHidden();
  await expect(snapshot).toContainText(newName);

  // A phone that is already a live card's: the card is shown and asked about; nothing is assigned
  // until the cashier chooses (F12: it may be another person with the same phone).
  await preview.locator('[data-testid=customer-search-trigger]').click();
  await modal.locator('[data-testid=customer-picker-search] input').fill(`${phone.slice(0, 3)} ${phone.slice(3)}`);
  await modal.locator('[data-testid=customer-search-quick-add]').click();
  await expect(inputOf(modal, 'customer-search-quick-phone')).toHaveValue(`${phone.slice(0, 3)} ${phone.slice(3)}`);
  await inputOf(modal, 'customer-search-quick-name').fill(e2eName('Should not exist'));
  await modal.locator('[data-testid=customer-search-quick-submit]').click();
  const taken = modal.locator('[data-testid=customer-search-phone-taken]');
  await expect(taken).toContainText(card.name);
  await page.screenshot({ path: shot('customer-search-phone-taken') });
  await taken.locator(`[data-testid=customer-search-use-${card.id}]`).click();
  await expect(modal).toBeHidden();
  await expect(snapshot).toContainText(card.name);

  // «Remove customer».
  await preview.locator('[data-testid=customer-search-trigger]').click();
  await modal.locator('[data-testid=customer-search-remove]').click();
  await expect(preview.locator('[data-testid=customer-preview-none]')).toBeVisible();
  await expect(preview.locator('[data-testid=customer-search-trigger]')).toHaveText(/Assign customer|Asignar cliente/);
});

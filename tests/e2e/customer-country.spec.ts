// The country of the card (CUSTOMER-F01, F04) on the real stack: the shared Combo (the product's
// `ok-combo`, customers#72). Typing part of its name filters the list under the field; the card keeps
// the two-letter code. Clearing the field, with the mouse or with the keyboard, leaves the card
// without a country. The list is seen open at 390×844, 834×1112 and 1440×900.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { cardOf, cleanUp, createCard, customersReady, e2eName, FLOW_VIEWPORTS, idFromUrl, inputOf, rowNamed, searchList } from './customer-helpers';
import { A, login, shot, shown } from './helpers';

test.afterAll(() => cleanUp());

const option = (page: Page, code: string): Locator => page.locator(`[data-testid=customer-form-country-option-${code}]`);
const countryOf = async (context: Parameters<typeof cardOf>[0], id: string): Promise<string> =>
  ((await cardOf(context, id)).data as unknown as { country: string }).country;

// flow: CUSTOMER-F01 — «País» filters while typing and stores the code
test('CUSTOMER-F01: the country is picked by typing part of its name, and the card keeps its code', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  await customersReady(page);
  await shown(page).locator('[data-testid=customer-list-add]').click();
  const dialog = page.locator('ion-modal[data-testid=customer-create]');
  await expect(dialog).toBeVisible();
  const name = e2eName('Country Ana');
  await inputOf(dialog, 'customer-form-name').fill(name);
  await dialog.locator('[data-testid=customer-form-more] > summary').click();
  const country = inputOf(dialog, 'customer-form-country');

  // At each size: the list opens under the field, filtered by what was typed; Escape closes only it.
  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await country.scrollIntoViewIfNeeded();
    await country.fill('fra');
    await expect(option(page, 'FR')).toBeVisible();
    await expect(option(page, 'FR')).toContainText(/France|Francia/);
    await expect(option(page, 'DE')).toHaveCount(0);
    // The list's entrance animation has ended: what the screenshot shows is what the person sees.
    await expect(page.locator('ion-popover.combo__popover .popover-content')).toHaveCSS('opacity', '1');
    await page.screenshot({ path: shot(`FIX-CUSTOMER-COUNTRY-SELECT-TO-COMBO-${vp.label}`) });
    await country.press('Escape');
    await expect(option(page, 'FR')).toHaveCount(0);
    await expect(dialog).toBeVisible();
    await expect(country).toHaveValue('');
  }

  await country.fill('fra');
  await option(page, 'FR').click();
  await expect(country).toHaveValue(/France|Francia/);
  await dialog.locator('[data-testid=customer-create-submit]').click();
  await expect(dialog).toBeHidden();

  await searchList(page, 'customer-list', name);
  await rowNamed(page, 'customer-list', name).click();
  await page.waitForURL(/\/customer\/customers\/[0-9a-f-]+$/);
  expect(await countryOf(context, idFromUrl(page))).toBe('FR');
});

// flow: CUSTOMER-F04 — clearing «País» (mouse or keyboard) leaves the card without a country
test('CUSTOMER-F04: clearing the country, with the mouse or the keyboard, saves the card without one', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('Country Edit'), country: 'FR' });
  await page.goto(`/customer/customers/${card.id}`);
  await shown(page).locator('[data-testid=customer-detail-edit]').click();
  const form = shown(page).locator('[data-testid=customer-edit-form]');
  const country = inputOf(form, 'customer-form-country');
  const clear = form.locator('[data-testid=customer-form-country-clear]');
  await expect(country).toHaveValue(/France|Francia/);

  // The mouse: the clear button empties the field.
  await clear.click();
  await expect(country).toHaveValue('');
  await expect(clear).toBeHidden();

  // The keyboard: typing and Enter pick; Tab reaches the clear button and Enter empties the field.
  await country.fill('portu');
  await expect(option(page, 'PT')).toBeVisible();
  await country.press('Enter');
  await expect(country).toHaveValue('Portugal');
  await country.press('Tab');
  await expect(clear).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(country).toHaveValue('');

  await shown(page).locator('[data-testid=customer-edit-save]').click();
  await expect(page.locator('ion-toast').last()).toContainText(/Customer updated|Cliente actualizado/);
  await expect.poll(() => countryOf(context, card.id)).toBe('');
});

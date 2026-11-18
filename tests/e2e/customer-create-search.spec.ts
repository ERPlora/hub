// CUSTOMER-F01, F02, F11 in Ioan's Chrome: «Add» on Customers opens «New customer»; a phone typed the
// Spanish way, without prefix, is saved in E.164 and painted grouped; a phone that is not one of its
// country is refused under «Phone» with what was typed kept; the list finds the card by its name,
// its phone however it is typed, and its email. The figures above the list count it live.
import { expect, test } from '@playwright/test';

import { cardOf, cleanUp, customersReady, e2eName, idFromUrl, inputOf, rowNamed, searchList, spanishMobile } from './customer-helpers';
import { A, login, shot, shown } from './helpers';

test.afterAll(() => cleanUp());

test('add a customer with a Spanish phone (saved in E.164), refuse an invalid one under its field, find it by name, phone and email', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  await customersReady(page);
  const before = Number(await shown(page).locator('[data-testid=customer-stats-total]').getAttribute('data-value'));

  // «Add» → «New customer»: name, phone, email, tax id, company in sight; the rest behind «More details».
  await shown(page).locator('[data-testid=customer-list-add]').click();
  const dialog = page.locator('ion-modal[data-testid=customer-create]');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('[data-testid=customer-create-submit]')).toHaveJSProperty('disabled', true);
  const name = e2eName('Ana García');
  const phone = spanishMobile();
  const email = `${name.replace(/[^a-z0-9]/gi, '').toLowerCase()}@example.com`;

  // A phone that is not one of its country: 422 under «Phone», what was typed kept, the dialog open.
  await inputOf(dialog, 'customer-form-name').fill(name);
  await inputOf(dialog, 'customer-form-phone').fill('600111');
  await dialog.locator('[data-testid=customer-create-submit]').click();
  const phoneField = dialog.locator('[data-testid=customer-form-phone]');
  await expect(phoneField).toHaveClass(/ion-invalid/);
  await expect.poll(() => phoneField.evaluate((el) => (el as HTMLElement & { errorText?: string }).errorText ?? '')).toMatch(/phone|teléfono/i);
  await expect(inputOf(dialog, 'customer-form-phone')).toHaveValue('600111');
  await page.screenshot({ path: shot('customer-create-invalid-phone') });

  // The phone as people say it, without prefix: saved as +34…
  await inputOf(dialog, 'customer-form-phone').fill(`${phone.slice(0, 3)} ${phone.slice(3, 6)} ${phone.slice(6)}`);
  await inputOf(dialog, 'customer-form-email').fill(email);
  await dialog.locator('[data-testid=customer-create-submit]').click();
  await expect(dialog).toBeHidden();

  // The live list and figures paint it by themselves.
  await searchList(page, 'customer-list', name);
  const row = rowNamed(page, 'customer-list', name);
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid=customer-list-phone]')).toHaveText(`+34 ${phone.slice(0, 3)} ${phone.slice(3, 6)} ${phone.slice(6)}`);
  await expect.poll(async () => Number(await shown(page).locator('[data-testid=customer-stats-total]').getAttribute('data-value'))).toBe(before + 1);

  // Server-side evidence: E.164.
  await row.click();
  await page.waitForURL(/\/customer\/customers\/[0-9a-f-]+$/);
  const id = idFromUrl(page);
  const saved = await cardOf(context, id);
  expect(saved.data.phone).toBe(`+34${phone}`);
  await expect(shown(page).locator('[data-fact=phone] dd')).toHaveText(`+34 ${phone.slice(0, 3)} ${phone.slice(3, 6)} ${phone.slice(6)}`);

  // Search: by name (no accents, any case), by the phone however it is typed, by email.
  await page.goto('/customer/customers');
  await customersReady(page);
  for (const term of [name.replace('García', 'garcia').toUpperCase(), `0034 ${phone.slice(0, 3)}-${phone.slice(3)}`, `+34 ${phone}`, email]) {
    await searchList(page, 'customer-list', term);
    await expect(rowNamed(page, 'customer-list', name), term).toBeVisible();
    await expect(shown(page).locator('[data-testid=customer-list-row]'), term).toHaveCount(1);
  }
  await searchList(page, 'customer-list', `${name} nobody`);
  await expect(shown(page).locator('[data-testid=customer-list-empty]')).toContainText(/No results|Sin resultados/);
  await page.screenshot({ path: shot('customer-search-no-results') });
});

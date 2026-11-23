// A customer's birthday without its year (CUSTOMER-F01, F03, F04), in Spanish on the real stack: the owner types
// «12» and «3» and leaves the year empty, saves, and the card shows «12 de marzo»; editing a card drops a year it
// should not have had. Seen at the three sizes, with no sideways scroll.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { cleanUp, createCard, customersReady, e2eName, FLOW_VIEWPORTS, horizontalOverflow, inputOf } from './customer-helpers';
import { A, login, psql, shot, shown } from './helpers';
import { toastSaying } from './toast-helpers';

test.afterAll(() => cleanUp());

async function inSpanish(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/customer/customers');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  return { context, page };
}

/** Types a day of the card into its three fields; an empty part is left empty. */
async function typeDay(scope: Locator, testid: string, parts: { day: string; month: string; year: string }): Promise<void> {
  for (const [part, value] of Object.entries(parts)) await inputOf(scope, `${testid}-${part}`).fill(value);
}

/** At each of the three sizes: `target` in sight, no sideways scroll, and the screenshot. */
async function threeShots(page: Page, key: string, target: Locator): Promise<void> {
  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(async () => {
      await target.scrollIntoViewIfNeeded({ timeout: 2000 });
      await expect(target).toBeInViewport({ timeout: 1000 });
    }, `${key} at ${vp.label}`).toPass();
    await expect.poll(() => horizontalOverflow(page), `sideways scroll at ${vp.label}`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`${key}-${vp.label}`) });
  }
}

const birthdayShown = (page: Page): Locator => shown(page).locator('[data-testid=customer-facts]').getByText('12 de marzo', { exact: true });

// flow: CUSTOMER-F01, CUSTOMER-F03 — a birthday is a day and a month; the year only if it is known
test('CUSTOMER-F01: a birthday typed without its year is saved and shown as «12 de marzo»', async ({ browser }) => {
  const { context, page } = await inSpanish(browser);
  try {
    await page.reload();
    await customersReady(page);
    await shown(page).locator('[data-testid=customer-list-add]').click();
    const dialog = page.locator('ion-modal[data-testid=customer-create]');
    const name = e2eName('F01 Birthday');
    await inputOf(dialog, 'customer-form-name').fill(name);
    await dialog.locator('[data-testid=customer-form-more] summary').click();
    const birthday = dialog.locator('[data-testid=customer-form-birthday]');
    await expect(birthday.locator('legend')).toHaveText('Cumpleaños');
    await typeDay(dialog, 'customer-form-birthday', { day: '12', month: '3', year: '' });
    await threeShots(page, 'CUSTOMER-F01-BIRTHDAY-WITHOUT-YEAR', birthday);
    await dialog.locator('[data-testid=customer-create-submit]').click();
    await expect(dialog).toBeHidden();
    const id = psql(`select id from customer_customer where name = '${name}'`);
    expect(psql(`select birthday from customer_customer where id = '${id}'`)).toBe('--03-12');
    await page.goto(`/customer/customers/${id}`);
    await expect(birthdayShown(page)).toBeVisible();
    await threeShots(page, 'CUSTOMER-F03-BIRTHDAY-WITHOUT-YEAR', birthdayShown(page));
  } finally {
    await context.close();
  }
});

// flow: CUSTOMER-F04 — emptying the year of a saved birthday keeps its day and its month
test('CUSTOMER-F04: «Edit» drops the year of a birthday and the card shows the day and the month', async ({ browser }) => {
  const { context, page } = await inSpanish(browser);
  try {
    const card = await createCard(context, { name: e2eName('F04 Birthday'), birthday: '1990-03-12' });
    await page.goto(`/customer/customers/${card.id}`);
    await shown(page).locator('[data-testid=customer-detail-edit]').click();
    const form = shown(page).locator('[data-testid=customer-edit-form]');
    await expect(inputOf(form, 'customer-form-birthday-year')).toHaveValue('1990');
    await inputOf(form, 'customer-form-birthday-year').fill('');
    await threeShots(page, 'CUSTOMER-F04-BIRTHDAY-WITHOUT-YEAR', form.locator('[data-testid=customer-form-birthday]'));
    await shown(page).locator('[data-testid=customer-edit-save]').click();
    await expect(toastSaying(page, /Cliente actualizado/)).toBeVisible();
    await expect(birthdayShown(page)).toBeVisible();
    expect(psql(`select birthday from customer_customer where id = '${card.id}'`)).toBe('--03-12');
  } finally {
    await context.close();
  }
});

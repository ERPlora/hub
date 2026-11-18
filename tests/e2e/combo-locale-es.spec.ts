// flow: combo-locale — hub#664 (COMBO-F02): Django joins every app's Spanish catalogue and the first that translates a
// message wins, so a VAT category that no longer exists read Sale's «categoría fiscal» under a field called «Tipo de
// IVA». The owner picks a category in the menu form, it is deactivated in Taxes meanwhile, and saving says the server's
// refusal under the field in the menu's own words. In Spanish, at 390, 834 and 1440. What this file makes carries its
// own key prefix and goes away.
import { expect, test } from '@playwright/test';

import { A, capture, login, psql, shown } from './helpers';
import { FLOW_VIEWPORTS, freshCategory, pickCombo } from './tax-helpers';

const KEY = 'ISSUE-664-COMBO-VAT-CATEGORY-IN-SPANISH';
const PREFIX = 'combo_locale';
/** combo's catalogue (`apps/combo/locale/es/LC_MESSAGES/django.po`), letter by letter. */
const REFUSED = 'Ese tipo de IVA no existe en Impuestos.';
const FIELD = 'combo-menu-form-tax_category';

function cleanUp(): void {
  psql(`delete from tax_taxcategory where key like 'e2e.${PREFIX}_%'`);
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('combo-locale: a VAT category gone meanwhile is refused under its field as «tipo de IVA»', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1440, height: 900 }, locale: 'es-ES' });
  const page = await context.newPage();
  try {
    await login(page, A, '/combo/menus');
    await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
    const key = await freshCategory(context, PREFIX);

    await page.goto(`${A}/combo/menus`);
    await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
    await shown(page).locator('[data-testid=combo-menus-add]').click();
    const form = page.locator('ion-modal[data-testid=combo-menu-form]');
    await expect(form).toBeVisible();
    await form.locator('[data-testid=combo-menu-form-name] input').first().fill(`E2E ${PREFIX}`);
    await form.locator('[data-testid=combo-menu-form-price] input').first().fill('13,50');
    await pickCombo(page, form, FIELD, key, key);

    // Someone deactivates it in Taxes first.
    psql(`update tax_taxcategory set is_active = false where key = '${key}'`);
    await form.locator('[data-testid=combo-menu-form-submit]').click();

    const field = form.locator(`[data-testid=${FIELD}]`);
    const error = field.locator('.error-text');
    await expect(error).toHaveText(REFUSED);
    await expect(field).toContainText('Tipo de IVA');
    await expect(form).toBeVisible();

    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await error.scrollIntoViewIfNeeded();
      await expect(error).toHaveText(REFUSED);
      await capture(page, `${KEY}-${viewport.label}`);
    }
  } finally {
    await context.close();
  }
});

// hub#760 — «New menu» fits the window at every size (COMBO-F02), in Chrome, against hub `a`. Each size is a new
// browser context, the form opened there, never a window resized with the form open. In Spanish «How is it sold?»
// chooses «Se consume en el local (servicio de restauración)», wider than a phone, and its one line used to set the
// width of every field: 387 px at 375 and 390, the fields cut on the right and, at 375, on the left too. So this
// measures each field and each help line against the dialog, not the page's overflow, which the clipped fields never
// raised. The chosen text can be read whole, either way of selling. Nothing is saved.
// flow: COMBO-F02
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, capture, login, painted, shown } from './helpers';

const VIEWPORTS = [
  { label: '375x667', width: 375, height: 667 },
  { label: '390x844', width: 390, height: 844 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
];
const LANGUAGES = ['es', 'en'] as const;
const FORM = 'ion-modal[data-testid=combo-menu-form]';
const SUPPLY = '[data-testid=combo-menu-form-supply_kind]';

async function openForm(browser: Browser, viewport: { width: number; height: number }, language: string) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/combo/menus');
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/combo/menus`);
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language}`));
  await shown(page).locator('[data-testid=combo-menus-add]').click();
  await expect(page.locator(FORM)).toBeVisible();
  await expect(page.locator(SUPPLY)).toBeVisible();
  return { context, page };
}

/** What the person cannot reach or read: the dialog past the screen, the body scrolling sideways, a field or a help
 *  line past the dialog (its hook and by how many px), the chosen way of selling cut short. Empty when all fits. */
function cutOff(page: Page): Promise<string[]> {
  return page.evaluate(
    ({ form, supply }) => {
      const cut: string[] = [];
      const modal = document.querySelector(form);
      const dialog = modal?.shadowRoot?.querySelector('.modal-wrapper')?.getBoundingClientRect();
      const body = modal?.querySelector('.ep-form-modal__body');
      if (!modal || !dialog || !body) return ['the form is not open'];
      if (dialog.left < 0 || dialog.right > window.innerWidth) cut.push(`dialog ${dialog.left}..${dialog.right}`);
      if (body.scrollWidth > body.clientWidth) cut.push(`body scrolls ${body.scrollWidth - body.clientWidth}px sideways`);
      for (const field of body.querySelectorAll('[data-testid]')) {
        const box = field.getBoundingClientRect();
        if (box.width === 0) continue;
        const hook = field.getAttribute('data-testid');
        if (dialog.left - box.left > 1) cut.push(`${hook} -${Math.round(dialog.left - box.left)}px`);
        if (box.right - dialog.right > 1) cut.push(`${hook} +${Math.round(box.right - dialog.right)}px`);
      }
      const chosen = modal.querySelector(supply)?.shadowRoot?.querySelector('[part~="text"]');
      if (!chosen?.textContent?.trim()) cut.push('no way of selling chosen');
      else if (chosen.scrollWidth > chosen.clientWidth) cut.push(`«${chosen.textContent}» cut short`);
      return cut;
    },
    { form: FORM, supply: SUPPLY },
  );
}

for (const language of LANGUAGES) {
  for (const viewport of VIEWPORTS) {
    test(`COMBO-F02: «New menu» fits the window at ${viewport.label} in ${language}, either way of selling`, async ({ browser }) => {
      const { context, page } = await openForm(browser, viewport, language);
      await expect.poll(() => cutOff(page), { message: 'eaten in, as the form opens' }).toEqual([]);
      await capture(page, `FIX-HUB-COMBO-MENU-FORM-FITS-${language}-${viewport.label}`);

      await page.locator(SUPPLY).click();
      await page.locator('ion-select-popover ion-radio').nth(1).click();
      await expect(page.locator('[data-testid=combo-menu-form-help-goods]')).toHaveAttribute('data-active', 'true');
      await expect(page.locator('ion-select-popover')).toHaveCount(0);
      await painted(page);
      await expect.poll(() => cutOff(page), { message: 'to take away, once chosen' }).toEqual([]);
      await context.close();
    });
  }
}

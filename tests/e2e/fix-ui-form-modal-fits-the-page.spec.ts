// flow: STAFF-F01 — a tall form in its window (FormModal of @erplora/ui) fits the page it opens on (hub#2012). In
// Chrome on an Android tablet in landscape the address bar leaves the page 665 px high while `100vh` still counts 721;
// with the interface at 120 % (My profile zooms the whole page) `100vh` grows with it, past the window. The window fits
// the page either way, its fields scroll between the title and the buttons, and its ✕, Save and Cancel stay on view;
// the same at 1280×665 and at the fleet's three sizes, with a screenshot at each. It saves nothing.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { capture, shown, signedInSpanish } from './helpers';
import { presentedDialog } from './inventory-helpers';
import { CHROME_LANDSCAPE, expectWindowFitsAt, expectWindowOnScreen, underAddressBar, type WindowFit, windowFit } from './screen';

const FORM = 'staff-member-form';
const SIZES = [
  { width: CHROME_LANDSCAPE.width, height: CHROME_LANDSCAPE.page },
  { width: 1440, height: 900 },
  { width: 834, height: 1194 },
  { width: 375, height: 667 },
] as const;
const ON_VIEW = ['✕', 'Save', 'Cancel', 'footer'] as const;

function fitOf(form: Locator): Promise<WindowFit> {
  return windowFit(form, {
    '✕': `[data-testid=${FORM}-close]`,
    Save: `[data-testid=${FORM}-submit]`,
    Cancel: `[data-testid=${FORM}-cancel]`,
    footer: '.ep-form-modal__footer',
  });
}

/** How much more the form's fields hold than what their part of the window shows: above 0, they scroll. */
function hiddenFields(form: Locator): Promise<number> {
  return form.locator('.ep-form-modal__body').evaluate((body) => body.scrollHeight - body.clientHeight);
}

function openNewProfessional(page: Page): Promise<Locator> {
  return presentedDialog(page, FORM, () => shown(page).locator('[data-testid=staff-members-add]').click());
}

test('STAFF-F01: in Chrome on a tablet in landscape, under the address bar, «New» professional fits the page with its ✕ and Save on view', async ({
  browser,
}) => {
  const viewport = { width: CHROME_LANDSCAPE.width, height: CHROME_LANDSCAPE.withoutBar };
  const { context, page } = await signedInSpanish(browser, viewport, '/staff/members');
  const bar = await underAddressBar(page);
  const form = await openNewProfessional(page);
  await expect(form.locator(`[data-testid=${FORM}-first_name]`)).toBeVisible();

  const fit = await fitOf(form);
  expect(fit.screen, 'the page is as tall as the screen under the address bar').toBe(CHROME_LANDSCAPE.page);
  expect(await hiddenFields(form), 'a form taller than the page: its fields scroll').toBeGreaterThan(0);
  expectWindowOnScreen(fit, ON_VIEW, 'under the address bar');
  await capture(page, 'FIX-UI-FORM-MODAL-FITS-THE-PAGE-staff-1280x665-chrome');

  await bar.evaluate((style) => (style as Element).remove());
  await expectWindowFitsAt(page, { sizes: SIZES, measure: () => fitOf(form), onView: ON_VIEW, name: 'FIX-UI-FORM-MODAL-FITS-THE-PAGE-staff' });
  await context.close();
});

test('STAFF-F01: with the interface at 120 %, «New» professional fits a 1280x665 window with its ✕ and Save on view', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, SIZES[0], '/staff/members');
  // What the scale of My profile does, for this page only: the owner's saved scale stays as it is.
  await page.evaluate(() => {
    document.documentElement.style.zoom = '120%';
  });
  const form = await openNewProfessional(page);
  await expect(form.locator(`[data-testid=${FORM}-first_name]`)).toBeVisible();

  const fit = await fitOf(form);
  expect(fit.screen, 'the page fills the window').toBe(CHROME_LANDSCAPE.page);
  expectWindowOnScreen(fit, ON_VIEW, 'at 120 %');
  await capture(page, 'FIX-UI-FORM-MODAL-FITS-THE-PAGE-staff-1280x665-scale-120');
  await context.close();
});

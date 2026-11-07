// The end of every settings page of the Hub is one piece (hub#897: `SettingsFormFooter` of @erplora/ui, after
// `useSettingsForm`): the refusal's red notice and «Settings saved» right above «Save», and «Save» at the end of the
// form at its own width, as a form window's (FormModal) and as Staff and Time clock had it — no longer a bar as long
// as the form in the other six. Measured on a desktop and on a phone, in each of the eight pages; the screenshots of
// the sweep (ui-clip-sweep.sh) show the rest. And on a phone every one of them fits the screen, in English and in
// Spanish: Tables (hub#866: 378 px wide in English, 425 in Spanish, «Guardar» cut to «Gua») and Reservations in English
// (hub#906: 382 px) ran past the screen's edge, a switch's long label on one line widening the whole form. Whatever
// this file turns on, it turns off again (hub#480).
// flow: APPOINTMENT-F19, ATTENDANCE-F04, KITCHEN-F26, ONLINE_BOOKING-F07, RESERVATION-F03, SERVICE-F11, STAFF-F22, TABLE-F08
import { type Page, expect, test } from '@playwright/test';

import { A, capture, horizontalOverflow, login, shown, signedInSpanish, turnOffTurnedOn, turnOnMissing } from './helpers';
import { ownerPage } from './service-helpers';

/** Each settings page and the prefix of its hooks (`<hook>-save`). */
const PAGES = [
  { path: '/appointment/settings', hook: 'appointment-settings' },
  { path: '/attendance/settings', hook: 'attendance-settings' },
  { path: '/kitchen/settings', hook: 'kitchen-settings' },
  { path: '/online_booking/settings', hook: 'ob-settings' },
  { path: '/reservation/settings', hook: 'reservation-settings' },
  { path: '/service/settings', hook: 'service-settings' },
  { path: '/staff/settings', hook: 'staff-settings' },
  { path: '/table/settings', hook: 'table-settings' },
] as const;
/** The eight apps and what they require, in the order they can be turned on. */
const NEEDED = ['customer', 'tax', 'staff', 'service', 'schedule', 'appointment', 'attendance', 'sale', 'inventory', 'kitchen', 'online_booking', 'table', 'reservation'];
const PHONE = { width: 375, height: 667 } as const;
const VIEWPORTS = [
  { label: 'desktop', width: 1440, height: 900 },
  { label: 'phone', ...PHONE },
] as const;

const turnedOn: string[] = [];

test.beforeAll(async ({ browser }) => {
  const { context } = await ownerPage(browser, '/');
  await turnOnMissing(context, A, NEEDED, turnedOn).finally(() => context.close());
});

test.afterAll(async ({ browser }) => {
  const { context } = await ownerPage(browser, '/');
  await turnOffTurnedOn(context, A, turnedOn).finally(() => context.close());
});

test('every settings page ends with «Save» at the end of the form, at its own width', async ({ page }) => {
  await login(page, A, PAGES[0].path);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    for (const { path, hook } of PAGES) {
      await page.goto(`${A}${path}`);
      const save = shown(page).locator(`[data-testid="${hook}-save"]`);
      await expect(save, `${path} at ${vp.label}`).toBeVisible();
      const form = save.locator('xpath=ancestor::form[1]');
      const [button, whole] = await Promise.all([save.boundingBox(), form.boundingBox()]);
      if (!button || !whole) throw new Error(`${path} at ${vp.label}: «Save» or its form has no box`);
      const where = `${path} at ${vp.label}: «Save» ${Math.round(button.x)}+${Math.round(button.width)} in a form ${Math.round(whole.x)}+${Math.round(whole.width)}`;
      expect.soft(Math.abs(button.x + button.width - (whole.x + whole.width)), `${where} ends where the form ends`).toBeLessThanOrEqual(1);
      expect.soft(button.width, `${where} is as wide as its words, not a bar`).toBeLessThan(whole.width / 2);
    }
  }
});

/** Why the settings page on screen cannot be read whole on a phone: it scrolls sideways, its form is wider than the
 *  screen, a switch's words end in «…», «Save» ends past the screen's edge or something covers one of its ends.
 *  Empty when it all fits. */
async function cutOnAPhone(page: Page, hook: string): Promise<string[]> {
  const save = shown(page).locator(`[data-testid="${hook}-save"]`);
  await expect(save, hook).toBeVisible();
  const cut: string[] = [];
  const sideways = await horizontalOverflow(page);
  if (sideways > 0) cut.push(`it scrolls ${sideways}px sideways`);
  const inForm = await save.locator('xpath=ancestor::form[1]').evaluate((form) => {
    const found: string[] = [];
    const past = form.getBoundingClientRect().right - document.documentElement.clientWidth;
    if (past > 0) found.push(`the form ends ${Math.round(past)}px past the screen`);
    for (const toggle of form.querySelectorAll('ion-toggle')) {
      const label = toggle.shadowRoot?.querySelector<HTMLElement>('[part~="label"]');
      if (label && label.scrollWidth > label.clientWidth) {
        found.push(`the switch «${toggle.textContent?.trim()}» is cut ${label.scrollWidth - label.clientWidth}px short`);
      }
    }
    return found;
  });
  cut.push(...inForm);
  const button = await save.boundingBox();
  if (!button) throw new Error(`${hook}: «Save» has no box`);
  if (button.x + button.width > PHONE.width) cut.push(`«Save» ends ${Math.round(button.x + button.width - PHONE.width)}px past the screen`);
  // Brought into view, what lies at either end of «Save» is «Save» or, while it is off with nothing to save (Ionic lets
  // the taps of a disabled button through), its own row: nothing covers it and no part of it is off the screen.
  await save.scrollIntoViewIfNeeded();
  const missed = await save.evaluate((target) => {
    const box = target.getBoundingClientRect();
    const middle = box.top + box.height / 2;
    const reaches = (x: number) => {
      const there = document.elementFromPoint(x, middle);
      return there !== null && (target.contains(there) || there === target.parentElement);
    };
    return [box.left + 2, box.right - 2].filter((x) => !reaches(x)).length;
  });
  if (missed > 0) cut.push(`«Save» is covered or off the screen at ${missed === 2 ? 'both ends' : 'one end'}`);
  return cut;
}

for (const language of ['English', 'Spanish'] as const) {
  test(`on a phone, in ${language}, every settings page fits the screen: no sideways scroll, no switch cut short, «Save» whole`, async ({ browser }) => {
    const { context, page } = language === 'Spanish'
      ? await signedInSpanish(browser, PHONE, PAGES[0].path)
      : await ownerPage(browser, PAGES[0].path, PHONE);
    try {
      const cut: Record<string, string[]> = {};
      for (const { path, hook } of PAGES) {
        await page.goto(`${A}${path}`);
        const why = await cutOnAPhone(page, hook);
        if (why.length > 0) cut[path] = why;
        await capture(page, `settings-on-a-phone-${language.toLowerCase()}-${hook}`);
      }
      expect(cut, `${language} at ${PHONE.width}x${PHONE.height}`).toEqual({});
    } finally {
      await context.close();
    }
  });
}

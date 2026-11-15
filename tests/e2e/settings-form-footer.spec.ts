// The end of every settings page of the Hub is one piece (hub#897: `SettingsFormFooter` of @erplora/ui, after
// `useSettingsForm`): the refusal's red notice and «Settings saved» right above «Save», and «Save» at the end of the
// form at its own width, as a form window's (FormModal) and as Staff and Time clock had it — no longer a bar as long
// as the form in the other six. Measured on a desktop and on a phone, in each of the eight pages; the screenshots of
// the sweep (ui-clip-sweep.sh) show the rest. And on a phone every one of them fits the screen, in English and in
// Spanish: Tables (hub#866: 378 px wide in English, 425 in Spanish, «Guardar» cut to «Gua») and Reservations in English
// (hub#906: 382 px) ran past the screen's edge, a switch's long label on one line widening the whole form. Their number
// fields are one piece too (hub#982: `SettingsNumberField`): in every page, Inventory's included, a refused one turns red
// with its reason under it — and only that: the browser never judges the form on its own (hub#1237: «Save» showed its
// own bubble over the field, and Enter with a number out of range sent nothing and said only the bubble). Whatever this
// file turns on, it turns off again (hub#480).
// flow: APPOINTMENT-F19, ATTENDANCE-F04, INVENTORY-F19, KITCHEN-F26, ONLINE_BOOKING-F07, RESERVATION-F03, SERVICE-F11, STAFF-F22, TABLE-F08
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
/** A number field of each settings page that `-5` is refused in (both groups of Reservations), and the prefix of its
 *  page's hooks. Time clock judges its hours on screen before sending, and says it under the field the same way. */
const NUMBER_FIELDS = [
  { path: '/appointment/settings', hook: 'appointment-settings', field: 'appointment-settings-default_duration' },
  { path: '/attendance/settings', hook: 'attendance-settings', field: 'attendance-settings-auto_close_after_hours' },
  { path: '/inventory/settings', hook: 'inventory-settings', field: 'inventory-settings-threshold' },
  { path: '/kitchen/settings', hook: 'kitchen-settings', field: 'kitchen-settings-warning_minutes' },
  { path: '/online_booking/settings', hook: 'ob-settings', field: 'ob-settings-max_upcoming_per_customer' },
  { path: '/reservation/settings', hook: 'reservation-settings', field: 'reservation-settings-default_duration_minutes' },
  { path: '/reservation/settings', hook: 'reservation-settings', field: 'reservation-settings-min_party_size' },
  { path: '/service/settings', hook: 'service-settings', field: 'service-settings-default_duration' },
  { path: '/staff/settings', hook: 'staff-settings', field: 'staff-settings-default_break_duration' },
  { path: '/table/settings', hook: 'table-settings', field: 'table-settings-timer_warning_minutes' },
] as const;
/** The eight apps and what they require, in the order they can be turned on. */
const NEEDED = ['customer', 'tax', 'staff', 'service', 'schedule', 'appointment', 'attendance', 'sale', 'inventory', 'kitchen', 'online_booking', 'table', 'reservation'];
const PHONE = { width: 375, height: 667 } as const;
const VIEWPORTS = [
  { label: 'desktop', width: 1440, height: 900 },
  { label: 'phone', ...PHONE },
] as const;
/** The three sizes the fleet looks at. */
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
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

test('a refused number field turns red with its reason under it, in every settings page', async ({ page }) => {
  await login(page, A, NUMBER_FIELDS[0].path);
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const { path, hook, field } of NUMBER_FIELDS) {
    await page.goto(`${A}${path}`);
    const box = shown(page).locator(`[data-testid="${field}"]`);
    await box.locator('input').fill('-5');
    await shown(page).locator(`[data-testid="${hook}-save"]`).click();
    await expect(box, `${field} is red`).toHaveClass(/\bion-invalid\b/);
    await expect(box.locator('.error-text'), `${field} says why`).toHaveText(/\S/);
    await expect(box.locator('.error-text'), `${field} says why`).toBeVisible();
    await box.scrollIntoViewIfNeeded();
    await capture(page, `settings-refused-${field}`);
  }
});

/** Counts, from now on, the `invalid` events of the page on screen: the browser fires one at each control it finds out
 *  of its constraints (`min`, `max`, `step`…) right before it shows its own bubble and holds the submission back. */
async function countBrowserJudgements(page: Page): Promise<() => Promise<number>> {
  await page.evaluate(() => {
    const seen = window as unknown as { browserJudgements: number };
    seen.browserJudgements = 0;
    document.addEventListener('invalid', () => (seen.browserJudgements += 1), true);
  });
  return () => page.evaluate(() => (window as unknown as { browserJudgements: number }).browserJudgements);
}

test('the browser never judges a settings form on its own: «Save» or Enter with a number out of range says only the page’s reason', async ({ page }) => {
  await login(page, A, NUMBER_FIELDS[0].path);
  for (const size of SIZES) {
    await page.setViewportSize(size);
    for (const { path, hook, field } of NUMBER_FIELDS) {
      const where = `${field} at ${size.width}x${size.height}`;
      await page.goto(`${A}${path}`);
      const judgements = await countBrowserJudgements(page);
      const box = shown(page).locator(`[data-testid="${field}"]`);
      const input = box.locator('input');
      await input.fill('-5');
      await shown(page).locator(`[data-testid="${hook}-save"]`).click();
      expect(await judgements(), `${where}: «Save» left the browser to judge it (its own bubble)`).toBe(0);
      await expect(box, `${where}: «Save» marks it red`).toHaveClass(/\bion-invalid\b/);
      // Typing lifts the reason; Enter sends the form again (the browser held it back and said only its bubble), and
      // the reason is the page's again.
      await input.fill('-6');
      await expect(box, `${where}: a change lifts the red`).not.toHaveClass(/\bion-invalid\b/);
      await input.press('Enter');
      expect(await judgements(), `${where}: Enter left the browser to judge it (its own bubble, and nothing sent)`).toBe(0);
      await expect(box, `${where}: Enter sends and marks it red`).toHaveClass(/\bion-invalid\b/);
      await expect(box.locator('.error-text'), `${where}: Enter says why`).toHaveText(/\S/);
      if (field.startsWith('attendance-')) await capture(page, `settings-no-bubble-${field}-${size.width}x${size.height}`);
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

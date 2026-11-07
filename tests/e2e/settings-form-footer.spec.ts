// The end of every settings page of the Hub is one piece (hub#897: `SettingsFormFooter` of @erplora/ui, after
// `useSettingsForm`): the refusal's red notice and «Settings saved» right above «Save», and «Save» at the end of the
// form at its own width, as a form window's (FormModal) and as Staff and Time clock had it — no longer a bar as long
// as the form in the other six. Measured on a desktop and on a phone, in each of the eight pages; the screenshots of
// the sweep (ui-clip-sweep.sh) show the rest. On a phone, in English, two pages still run past the screen's edge
// (`SPILLS_ON_A_PHONE`, an issue each): there «Save» ends where the spilled row ends, so its end is measured on the
// desktop only, until its issue is fixed and the entry goes. Whatever this file turns on, it turns off again (hub#480).
// flow: APPOINTMENT-F19, ATTENDANCE-F04, KITCHEN-F26, ONLINE_BOOKING-F07, RESERVATION-F03, SERVICE-F11, STAFF-F22, TABLE-F08
import { expect, test } from '@playwright/test';

import { A, login, shown, turnOffTurnedOn, turnOnMissing } from './helpers';
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
/** The pages whose form runs past a phone's edge in English, with the issue that fixes it (not this footer's). */
const SPILLS_ON_A_PHONE: Record<string, string> = {
  '/reservation/settings': 'hub#906',
  '/table/settings': 'hub#866',
};
/** The eight apps and what they require, in the order they can be turned on. */
const NEEDED = ['customer', 'tax', 'staff', 'service', 'schedule', 'appointment', 'attendance', 'sale', 'inventory', 'kitchen', 'online_booking', 'table', 'reservation'];
const VIEWPORTS = [
  { label: 'desktop', width: 1440, height: 900 },
  { label: 'phone', width: 375, height: 667 },
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
      if (vp.label === 'desktop' || !SPILLS_ON_A_PHONE[path]) {
        expect.soft(Math.abs(button.x + button.width - (whole.x + whole.width)), `${where} ends where the form ends`).toBeLessThanOrEqual(1);
      }
      expect.soft(button.width, `${where} is as wide as its words, not a bar`).toBeLessThan(whole.width / 2);
    }
  }
});

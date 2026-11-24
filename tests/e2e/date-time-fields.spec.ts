// The pickers of date-time-fields.ts on a real TimeField: the time of «New appointment» in Appointments, in American
// English, so its wheel has AM and PM.
import { expect, test } from '@playwright/test';

import { pickTime, timeAsShown } from './date-time-fields';
import { shown } from './helpers';
import { ownerPage } from './service-helpers';
import { discardChanges } from './unsaved-back-helpers';

/** Each one in the other half of the day from the one before, whatever the clock says when the wheel first opens:
 *  every pick turns AM into PM, or back, before it taps the hour, and that redraws the hours of the wheel. */
const TIMES = ['10:15', '20:30', '09:45', '19:00', '11:30', '21:15'];

test('pickTime holds the hour it taps right after AM or PM redraws the hours of the wheel', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/appointment/agenda');
  try {
    await shown(page).locator('[data-testid=appointment-list-add]').click();
    const field = page.locator('ion-modal[data-testid=appointment-form] [data-testid=appointment-form-time]');
    for (const time of TIMES) {
      await pickTime(page, field, time);
      await expect(field.locator('input')).toHaveValue(timeAsShown(time));
    }
    await page.locator('[data-testid=appointment-form-cancel]').click();
    await discardChanges(page);
  } finally {
    await context.close();
  }
});

// Picking a day or a time in the date and time fields of @erplora/ui (DateField, TimeField, and the two of a
// DateTimeField) as a person does: a tap on the field opens Ionic's calendar or time wheel in a popover; the person
// moves to the month, taps the day (or the hour, the minute and AM/PM) and presses Done, or Clear to empty a field
// that is not required. The field then shows the value in the app's language.
import { expect, type Locator, type Page } from '@playwright/test';

/** Opens the picker of `field`: the ion-datetime of the popover it presents (Ionic hides the inline popovers that are
 *  not presented), once ready (before, the calendar does not move to another month). */
async function openPicker(page: Page, field: Locator, presentation: 'date' | 'time'): Promise<Locator> {
  await field.click();
  const picker = page.locator(`ion-popover.ep-picker-field__popover--${presentation}:not(.overlay-hidden) ion-datetime`);
  await expect(picker).toHaveClass(/datetime-ready/);
  return picker;
}

/** The month the calendar shows, as `year * 12 + month`: the middle one of the three it renders. */
async function shownMonth(picker: Locator): Promise<number> {
  const day = picker.locator('.calendar-month').nth(1).locator('.calendar-day[data-month]').first();
  const [year, month] = await Promise.all([day.getAttribute('data-year'), day.getAttribute('data-month')]);
  return Number(year) * 12 + Number(month);
}

async function confirm(picker: Locator): Promise<void> {
  await picker.locator('#confirm-button').click();
  await expect(picker).toBeHidden();
}

/** `day` (`YYYY-MM-DD`) as a DateField shows it to the specs' owner, who reads the Hub in American English. */
export function dayAsShown(day: string): string {
  const options = { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' } as const;
  return new Intl.DateTimeFormat('en-US', options).format(Date.parse(`${day}T00:00:00Z`));
}

/** `time` (`HH:MM`, 24 hours) as a TimeField shows it to the specs' owner, in American English («09:30 AM»). */
export function timeAsShown(time: string): string {
  const options = { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' } as const;
  return new Intl.DateTimeFormat('en-US', options).format(Date.parse(`1970-01-01T${time}:00Z`));
}

/** Picks `day` (`YYYY-MM-DD`) in the DateField `field`. */
export async function pickDay(page: Page, field: Locator, day: string): Promise<void> {
  const picker = await openPicker(page, field, 'date');
  const [year, month, date] = day.split('-').map(Number);
  const target = year * 12 + month;
  for (let moves = 0; moves < 24; moves++) {
    const shown = await shownMonth(picker);
    if (shown === target) break;
    const arrow = picker.locator('.calendar-next-prev ion-button').nth(shown < target ? 1 : 0);
    // A tap while the calendar still settles is lost: tap again until the month moves.
    await expect(async () => {
      if ((await shownMonth(picker)) === shown) await arrow.click();
      await expect.poll(() => shownMonth(picker), { timeout: 2_000 }).not.toBe(shown);
    }).toPass();
  }
  await picker.locator('.calendar-month').nth(1).locator(`.calendar-day[data-day="${date}"][data-month="${month}"]`).click();
  await confirm(picker);
}

/** Taps the option of the wheel `column` that reads `text` until the wheel holds it. A quarter of a second after a
 *  wheel last scrolls it takes the option then in its middle, undoing a tap made meanwhile: AM or PM redraws the hours
 *  and scrolls their wheel, so the hour tapped right after it is lost, and is tapped again as a person would. */
async function spin(picker: Locator, column: string, text: string): Promise<void> {
  const wheel = picker.locator(`ion-picker-column[aria-label="${column}"]`);
  const option = wheel.locator('ion-picker-column-option').filter({ hasText: new RegExp(`^${text}$`) });
  await expect(async () => {
    await option.click();
    await expect(option).toHaveClass(/option-active/, { timeout: 2_000 });
  }).toPass();
}

/** Picks `time` (`HH:MM`, 24 hours) in the TimeField `field`: on a wheel with AM and PM (a page in English) or on the
 *  24-hour wheel of a language that reads the clock that way, whose hours have two digits. */
export async function pickTime(page: Page, field: Locator, time: string): Promise<void> {
  const picker = await openPicker(page, field, 'time');
  const [hours, minutes] = time.split(':').map(Number);
  if (await picker.locator('ion-picker-column[aria-label="Select a day period"]').count()) {
    await spin(picker, 'Select a day period', hours < 12 ? 'AM' : 'PM');
    await spin(picker, 'Select an hour', String(hours % 12 || 12));
  } else {
    await spin(picker, 'Select an hour', String(hours).padStart(2, '0'));
  }
  await spin(picker, 'Select a minute', String(minutes).padStart(2, '0'));
  await confirm(picker);
}

/** Empties the DateField or TimeField `field` (one that is not required) with its picker's Clear. */
export async function clearPick(page: Page, field: Locator, presentation: 'date' | 'time'): Promise<void> {
  const picker = await openPicker(page, field, presentation);
  await picker.locator('#clear-button').click();
  await expect(picker).toBeHidden();
}

/** Picks `value` (`YYYY-MM-DDTHH:MM`) in the DateTimeField `pair` (its group): the day, then the time. */
export async function pickDayTime(page: Page, pair: Locator, value: string): Promise<void> {
  const [day, time] = value.split('T');
  await pickDay(page, pair.locator('ion-input').first(), day);
  await pickTime(page, pair.locator('ion-input').last(), time);
}

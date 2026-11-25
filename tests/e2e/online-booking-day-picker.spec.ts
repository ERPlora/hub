// flow: ONLINE_BOOKING-F01
// The day of the booking page (`/p/<slug>/book`, without a session) on a tablet held sideways, a phone, an upright
// tablet and a laptop: wherever the field is on the screen, its calendar shows whole, with Cancel, Clear and Done; the
// day tapped (or taken with the keyboard) is the one of the field, with its free times, and it is booked. Closing the
// calendar without taking a day leaves the field as it was.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { aMonday } from './appointment-helpers';
import { cutInPicker, dayIn, openPicker } from './date-time-fields';
import { A, capture, psql, settled } from './helpers';
import { cast, keepTheBusiness } from './online-booking-helpers';
import { ownerPage } from './service-helpers';

const TAG = 'E2E PD';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;
const PAGE = `${A}/p/a/book`;
keepTheBusiness(TAG);

const SIZES = [
  { label: 'tablet-sideways', width: 1280, height: 665, locale: 'en-US', at10: '10:00 AM' },
  { label: 'phone', width: 375, height: 667, locale: 'es-ES', at10: '10:00' },
  { label: 'tablet', width: 820, height: 1180, locale: 'es-ES', at10: '10:00' },
  { label: 'laptop', width: 1280, height: 720, locale: 'en-US', at10: '10:00 AM' },
] as const;
type Size = (typeof SIZES)[number];

const dayField = (page: Page) => page.locator('[data-testid=ob-preview-day]');

/** The booking page of a visitor without a session, at `size`, with its service chosen. */
async function bookingPage(browser: Browser, size: Size, service: string, n: number) {
  const context = await browser.newContext({
    viewport: { width: size.width, height: size.height },
    locale: size.locale,
    extraHTTPHeaders: { 'X-Forwarded-For': `10.${n + 11}.${Math.floor(Math.random() * 250)}.1` },
  });
  const page = await context.newPage();
  await page.goto(PAGE);
  await page.locator(`[data-testid=ob-preview-service-${service}]`).click();
  return { context, page };
}

/** `day` as the field shows it in the language of `size`. */
function asShown(day: string, size: Size): string {
  const options = { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' } as const;
  return new Intl.DateTimeFormat(size.locale, options).format(Date.parse(`${day}T00:00:00Z`));
}

SIZES.forEach((size, n) => {
  test(`the calendar of the day shows whole and the day tapped is booked at ${size.label}`, async ({ browser }) => {
    const { context: owner } = await ownerPage(browser, '/online_booking/bookings');
    const day = aMonday(n);
    try {
      const who = await cast(owner, named(size.label), day);
      const { context, page } = await bookingPage(browser, size, who.service.id, n);
      try {
        const field = dayField(page);
        const value = field.locator('input');

        for (const block of ['start', 'center', 'end'] as const) {
          await field.evaluate((el, at) => el.scrollIntoView({ block: at }), block);
          const picker = await openPicker(page, field, 'date');
          expect(await cutInPicker(picker), `cut with the field at the ${block} of the screen`).toEqual([]);
          const box = (await picker.boundingBox())!;
          expect(Math.abs(box.x + box.width / 2 - size.width / 2), 'off the middle, across').toBeLessThanOrEqual(1);
          expect(Math.abs(box.y + box.height / 2 - size.height / 2), 'off the middle, down').toBeLessThanOrEqual(1);
          if (block === 'center') await capture(page, `online-booking-day-picker-${size.label}`);
          await picker.locator('#cancel-button').click();
          await expect(picker).toBeHidden();
          await expect(value).toHaveValue('');
        }

        // Closed with the keyboard or by a tap outside it: no day.
        let picker = await openPicker(page, field, 'date');
        await page.keyboard.press('Escape');
        await expect(picker).toBeHidden();
        picker = await openPicker(page, field, 'date');
        // Ionic lets taps outside through once the popover has come in.
        await settled(page);
        await page.mouse.click(4, size.height - 4);
        await expect(picker).toBeHidden();
        await expect(value).toHaveValue('');

        // The day tapped is the field's, with no more to press, and its free times are offered.
        picker = await openPicker(page, field, 'date');
        await (await dayIn(picker, day)).click();
        await expect(picker).toBeHidden();
        await expect(value).toHaveValue(asShown(day, size));
        const ten = page.locator('[data-testid="ob-preview-time-10:00"]');
        await expect(ten).toHaveText(size.at10);
        await ten.click();
        const customer = named(`Marta ${size.label}`);
        await page.locator('[data-testid=ob-preview-name] input').fill(customer);
        await page.locator('[data-testid=ob-preview-phone] input').fill(`6${String(Date.now() + n * 7919).slice(-8)}`);
        await page.locator('[data-testid=ob-preview-book]').click();
        const booked = page.locator('[data-testid=ob-preview-booked]');
        await expect(booked).toContainText('APT-');
        const number = ((await booked.textContent()) ?? '').match(/APT-\d{8}-\d{4}/)![0];
        expect(psql(`select status from appointment_appointment where number = '${number}'`)).toBe('pending');
      } finally {
        await context.close();
      }
    } finally {
      await owner.close();
    }
  });
});

test('with the keyboard: the calendar opens, a day is taken with Enter and the focus is back on the field', async ({ browser }) => {
  const [size] = SIZES;
  const { context: owner } = await ownerPage(browser, '/online_booking/bookings');
  const day = aMonday(SIZES.length);
  try {
    const who = await cast(owner, named('keyboard'), day);
    const { context, page } = await bookingPage(browser, size, who.service.id, SIZES.length);
    try {
      const field = dayField(page);
      const value = field.locator('input');
      await value.focus();
      await page.keyboard.press('Enter');
      const picker = page.locator('ion-popover.ep-picker-field__popover--date:not(.overlay-hidden) ion-datetime');
      await expect(picker).toHaveClass(/datetime-ready/);
      const target = await dayIn(picker, day);
      await target.focus();
      await page.keyboard.press('Enter');
      await expect(picker).toBeHidden();
      await expect(value).toHaveValue(asShown(day, size));
      await expect(value).toBeFocused();
    } finally {
      await context.close();
    }
  } finally {
    await owner.close();
  }
});

test('moving through the months and the years takes no day until one is tapped, and Done keeps the same day of another month', async ({ browser }) => {
  const [size] = SIZES;
  const { context: owner } = await ownerPage(browser, '/online_booking/bookings');
  const day = aMonday(SIZES.length + 1);
  try {
    const who = await cast(owner, named('months'), day);
    const { context, page } = await bookingPage(browser, size, who.service.id, SIZES.length + 1);
    try {
      const field = dayField(page);
      const value = field.locator('input');
      let picker = await openPicker(page, field, 'date');
      await picker.locator('.calendar-next-prev ion-button').nth(1).click();
      await expect(picker).toBeVisible();
      await expect(value).toHaveValue('');
      await (await dayIn(picker, day)).click();
      await expect(picker).toBeHidden();

      picker = await openPicker(page, field, 'date');
      await picker.locator('.calendar-month-year-toggle').click();
      const years = picker.locator('ion-picker-column[aria-label="Select a year"]');
      const before = Number(day.slice(0, 4));
      await years.locator('ion-picker-column-option').filter({ hasText: new RegExp(`^${before - 1}$`) }).click();
      await expect(years.locator('ion-picker-column-option.option-active[part~="active"]')).toHaveText(String(before - 1));
      await expect(picker).toBeVisible();
      await expect(value).toHaveValue(asShown(day, size));
      await picker.locator('.calendar-month-year-toggle').click();
      await picker.locator('#confirm-button').click();
      await expect(picker).toBeHidden();
      await expect(value).toHaveValue(asShown(`${before - 1}${day.slice(4)}`, size));

      picker = await openPicker(page, field, 'date');
      await picker.locator('#clear-button').click();
      await expect(picker).toBeHidden();
      await expect(value).toHaveValue('');
    } finally {
      await context.close();
    }
  } finally {
    await owner.close();
  }
});

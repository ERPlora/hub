// The pickers of date-time-fields.ts on real fields: the day and the time of «New appointment» in Appointments, in
// American English, so the wheel of the time has AM and PM.
import { expect, test, type Browser, type Locator, type Page } from '@playwright/test';

import { cutInPicker, openPicker, pickTime, timeAsShown } from './date-time-fields';
import { shown } from './helpers';
import { ownerPage } from './service-helpers';
import { discardChanges } from './unsaved-back-helpers';

/** Each one in the other half of the day from the one before, whatever the clock says when the wheel first opens:
 *  every pick turns AM into PM, or back, before it taps the hour, and that redraws the hours of the wheel. */
const TIMES = ['10:15', '20:30', '09:45', '19:00', '11:30', '21:15'];

/** Ionic's hour wheel: `setValue` is what it calls itself on the option it settles on. */
type HourWheel = HTMLElement & { value: number; setValue(hour: number): Promise<void> };

/** Runs `body` on the form of a new appointment, at `viewport`, and leaves it without saving it. */
async function onNewAppointment(browser: Browser, body: (page: Page, form: Locator) => Promise<void>, viewport?: { width: number; height: number }): Promise<void> {
  const { context, page } = await ownerPage(browser, '/appointment/agenda', viewport);
  try {
    await shown(page).locator('[data-testid=appointment-list-add]').click();
    await body(page, page.locator('ion-modal[data-testid=appointment-form]'));
    await page.locator('[data-testid=appointment-form-cancel]').click();
    await discardChanges(page);
  } finally {
    await context.close();
  }
}

/** Runs `body` on the time field of a new appointment, and leaves the form without saving it. */
async function onTimeField(browser: Browser, body: (page: Page, field: Locator) => Promise<void>): Promise<void> {
  await onNewAppointment(browser, (page, form) => body(page, form.locator('[data-testid=appointment-form-time]')));
}

/** The next hour tapped is let go, as Ionic does with a tap made while the wheel settles: the wheel takes the hour but is
 *  not there yet; then, at the next tap or half a second later, it is back at the hour it had while the option tapped is
 *  the one that looks taken. */
async function letTheNextHourGo(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.addEventListener('click', function tapped(event) {
      const option = event.composedPath().find((node): node is HTMLElement =>
        node instanceof HTMLElement && node.matches('ion-picker-column[aria-label="Select an hour"] > ion-picker-column-option'));
      if (!option) return;
      document.removeEventListener('click', tapped);
      const wheel = option.parentElement as HourWheel;
      const before = wheel.querySelector('.option-active') as HTMLElement & { value: number };
      const track = wheel.shadowRoot!.querySelector('.picker-opts')!;
      const stay = () => track.scrollTo({ top: track.scrollTop, behavior: 'instant' });
      const letGo = () => {
        clearTimeout(timer);
        document.removeEventListener('click', letGo, true);
        void wheel.setValue(before.value);
        stay();
        const lookTaken = () => {
          if (option.part.contains('active')) return requestAnimationFrame(lookTaken);
          before.classList.remove('option-active');
          option.classList.add('option-active');
        };
        lookTaken();
      };
      const timer = setTimeout(letGo, 500);
      document.addEventListener('click', letGo, true);
      stay();
    });
  });
}

/** The wheel moves to the hour before as Done is tapped. */
async function moveTheHourAtDone(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.addEventListener('click', function move(event) {
      const path = event.composedPath().filter((node) => node instanceof HTMLElement);
      if (!path.some((node) => node.id === 'confirm-button')) return;
      document.removeEventListener('click', move, true);
      const picker = path.find((node) => node.localName === 'ion-datetime')!;
      const wheel = picker.shadowRoot!.querySelector('ion-picker-column[aria-label="Select an hour"]') as HourWheel;
      void wheel.setValue(wheel.value - 1);
    }, true);
  });
}

test('on a tablet held sideways the calendar and the wheel of a form show whole in the middle of the screen', async ({ browser }) => {
  const tablet = { width: 1280, height: 665 };
  await onNewAppointment(browser, async (page, form) => {
    const fields = { date: form.locator('[data-testid=appointment-form-day]'), time: form.locator('[data-testid=appointment-form-time]') };
    for (const presentation of ['date', 'time'] as const) {
      for (const block of ['start', 'center', 'end'] as const) {
        await fields[presentation].evaluate((el, at) => el.scrollIntoView({ block: at }), block);
        const picker = await openPicker(page, fields[presentation], presentation);
        expect(await cutInPicker(picker), `cut in the ${presentation} with its field at the ${block}`).toEqual([]);
        const box = (await picker.boundingBox())!;
        expect(Math.abs(box.x + box.width / 2 - tablet.width / 2), `${presentation}, across`).toBeLessThanOrEqual(1);
        expect(Math.abs(box.y + box.height / 2 - tablet.height / 2), `${presentation}, down`).toBeLessThanOrEqual(1);
        await page.keyboard.press('Escape');
        await expect(picker).toBeHidden();
      }
    }
    await pickTime(page, fields.time, '10:15');
  }, tablet);
});

test('pickTime holds the hour it taps right after AM or PM redraws the hours of the wheel', async ({ browser }) => {
  await onTimeField(browser, async (page, field) => {
    for (const time of TIMES) {
      await pickTime(page, field, time);
      await expect(field.locator('input')).toHaveValue(timeAsShown(time));
    }
  });
});

test('pickTime taps again the hour the wheel let go, though the hour still looks taken', async ({ browser }) => {
  await onTimeField(browser, async (page, field) => {
    await pickTime(page, field, '09:00');
    await letTheNextHourGo(page);
    await pickTime(page, field, '10:15');
    await expect(field.locator('input')).toHaveValue(timeAsShown('10:15'));
  });
});

test('pickTime does not go on with a field left at another hour', async ({ browser }) => {
  await onTimeField(browser, async (page, field) => {
    await pickTime(page, field, '09:00');
    await moveTheHourAtDone(page);
    await expect(pickTime(page, field, '10:15')).rejects.toThrow('toHaveValue');
    await expect(field.locator('input')).toHaveValue(timeAsShown('09:15'));
  });
});

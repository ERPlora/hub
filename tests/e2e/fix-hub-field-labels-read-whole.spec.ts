// hub#2374, hub#2277 — the label of a field that shares its row with another reads whole. Ionic keeps a floating label
// on one line ending in «…»: the record of a professional cut its buffer in English, before the word that says it goes
// in minutes, and «New time slot» cut its maximum of guests in both languages, before the word that says it is optional.
// Every label of both windows is measured against its own box, in English and in Spanish, on a phone, a tablet and a
// desk; in the record also with the buffer emptied, where the label takes its full size inside the field.
// flow: STAFF-F02, RESERVATION-F01
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { cutLabels } from './field-labels';
import { A, api, capture, hostPage, login, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { staffCleanUp } from './staff-helpers';

const SIZES = [
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
] as const;
const LANGS = ['en', 'es'] as const;
type Lang = (typeof LANGS)[number];

const TAG = 'E2E Label';
const NAME = { first_name: `${TAG} Daniel`, last_name: `Brooks ${Date.now().toString(36)}` };

const BUFFER = { en: 'Booking buffer (min)', es: 'Margen entre citas (min)' } as const;
const COVERS = { en: 'Max guests', es: 'Máx comensales' } as const;
const OPTIONAL = { en: 'Optional', es: 'Opcional' } as const;

test.beforeAll(async ({ browser }) => {
  staffCleanUp(TAG);
  const { context } = await hostPage(browser, A, { next: '/' });
  const made = await api(context, A, 'POST', '/staff/members', NAME);
  expect(made.status, JSON.stringify(made.data)).toBe(201);
  await context.close();
});

test.afterAll(() => staffCleanUp(TAG));

/** The owner on `next`, with the Hub in `lang`. */
async function ownerPage(browser: Browser, lang: Lang, next: string): Promise<Page> {
  if (lang === 'es') return (await signedInSpanish(browser, SIZES[2], next)).page;
  const context = await browser.newContext({ baseURL: A, viewport: SIZES[2], locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next);
  return page;
}

/** Every label of `form` reads whole at each size, captured as `name` with `field` on screen. */
async function expectWholeLabels(page: Page, form: Locator, field: Locator, name: string): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await field.scrollIntoViewIfNeeded();
    await capture(page, `${name}-${size.label}`);
    expect.soft(await cutLabels(form), `${name} at ${size.label}`).toEqual([]);
  }
}

for (const lang of LANGS) {
  test(`in ${lang}, every label of a professional's record reads whole, with the buffer filled in and emptied`, async ({ browser }) => {
    const page = await ownerPage(browser, lang, '/staff/members');
    try {
      await saveSessionForTheSweep(page.context());
      await shown(page).locator('[data-testid=staff-members-row]', { hasText: NAME.last_name }).getByText(NAME.last_name).click();
      const form = page.locator('ion-modal[data-testid=staff-member-form]');
      const buffer = form.locator('[data-testid=staff-member-form-booking_buffer]');
      await expect(buffer.locator('input')).toHaveValue('0');
      await expect.soft(buffer.locator('.label-text')).toHaveText(BUFFER[lang]);
      await expectWholeLabels(page, form, buffer, `STAFF-F02-labels-${lang}-filled`);
      await buffer.locator('input').fill('');
      await form.locator('[data-testid=staff-member-form-color] input').focus();
      await expectWholeLabels(page, form, buffer, `STAFF-F02-labels-${lang}-emptied`);
    } finally {
      await page.context().close();
    }
  });

  test(`in ${lang}, every label of «New time slot» reads whole and the maximum of guests says it is optional`, async ({ browser }) => {
    const page = await ownerPage(browser, lang, '/reservation/availability');
    try {
      await shown(page).locator('[data-testid=reservation-availability-slots-add]').click();
      const form = page.locator('ion-modal[data-testid=reservation-slot-form]');
      const covers = form.locator('[data-testid=reservation-slot-form-max_covers]');
      await expect.soft(covers.locator('.label-text')).toHaveText(COVERS[lang]);
      await expect.soft(covers.locator('.helper-text')).toHaveText(OPTIONAL[lang]);
      await expectWholeLabels(page, form, covers, `RESERVATION-F01-labels-${lang}-empty`);
      await covers.locator('input').fill('40');
      await expectWholeLabels(page, form, covers, `RESERVATION-F01-labels-${lang}-typed`);
    } finally {
      await page.context().close();
    }
  });
}

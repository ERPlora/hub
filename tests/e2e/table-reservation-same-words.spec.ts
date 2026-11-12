// flow: TABLE-F01, RESERVATION-F06 — hub#888: in a window, fields refused with the same words lose their marks one by
// one as each is corrected, in Tables and Reservations too: every field carries the name the server refuses it by, so
// the window tells which refused field a keystroke corrects. Seen in Tables › Zones › «+» (a window that paints its
// own footer: Delete · Cancel · Save) and in Reservations › «New reservation», at 390, 834 and 1440: the save is
// refused for three fields with the same words; typing in one takes the mark from it alone, then another, and the
// third keeps its own. The refusal is answered in the browser (`page.route`), so nothing is created. Once more in
// Spanish, whose session the fleet's visual sweep reads (`E2E_SAVE_STORAGE_STATE`).
import { expect, type Locator, type Page, test } from '@playwright/test';

import { capture, psql, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { expectMarked, expectUnmarked, refuseWithTheSameWords } from './same-words-helpers';
import { stamp, VIEWPORTS } from './sale-helpers';
import { ownerPage } from './service-helpers';

const TAG = `E2E888 ${stamp()}`;

/** A window of the test: where it opens, the save it sends, and the three fields it refuses, in the order corrected. */
interface Window {
  /** The screenshots' app: `CLOSE-<app>-hub888-<step>-<label>`. */
  app: 'TABLE' | 'RESERVATION';
  page: string;
  add: string;
  testid: string;
  /** The save (POST) the window sends, answered in the browser. */
  save: string;
  /** Fills what the window needs before «Save» is on. */
  fill: (form: Locator) => Promise<void>;
  /** The keys refused, in the order they are corrected (typed again); the last one keeps its mark. */
  keys: readonly [string, string, string];
  /** What nothing reached the Hub reads as 0. */
  created: string;
}

const ZONE: Window = {
  app: 'TABLE',
  page: '/table/zones',
  add: 'table-zones-add',
  testid: 'table-zone-form',
  save: '**/api/table/zones',
  fill: async (form) => {
    await form.locator('[data-testid=table-zone-form-name] input').fill(`${TAG} Terrace`);
    await form.locator('[data-testid=table-zone-form-description] input').fill('By the window');
  },
  keys: ['sort_order', 'name', 'description'],
  created: `select count(*) from table_zone where name like '${TAG}%'`,
};

const RESERVATION: Window = {
  app: 'RESERVATION',
  page: '/reservation/reservations',
  add: 'reservation-list-add',
  testid: 'reservation-form',
  save: '**/api/reservation/reservations',
  fill: async (form) => {
    await form.locator('[data-testid=reservation-form-guest_name] input').fill(`${TAG} Ana`);
    await form.locator('[data-testid=reservation-form-guest_phone] input').fill('600111222');
    await form.locator('[data-testid=reservation-form-time] input').fill('21:00');
  },
  keys: ['guest_phone', 'guest_name', 'time'],
  created: `select count(*) from reservation_reservation where guest_name like '${TAG}%'`,
};

/** In `window`, its three fields refused with the same `words` lose their marks one by one as each is typed again;
 *  the last keeps its own. Screenshots `CLOSE-<app>-hub888-<step>-<label>`. */
async function correctOneByOne(page: Page, window: Window, words: string, label: string): Promise<void> {
  const marked = (field: Locator): Promise<void> => expectMarked(field, words);
  const unmarked = (field: Locator): Promise<void> => expectUnmarked(field, words);
  await shown(page).locator(`[data-testid=${window.add}]`).click();
  const form = page.locator(`ion-modal[data-testid=${window.testid}]`);
  await expect(form).toBeVisible();
  await window.fill(form);
  const [first, second, last] = window.keys.map((key) => form.locator(`[data-testid=${window.testid}-${key}]`));

  await refuseWithTheSameWords(page, window.save, window.keys, words);
  await form.locator(`[data-testid=${window.testid}-submit]`).click();
  for (const field of [first, second, last]) await marked(field);
  await capture(page, `CLOSE-${window.app}-hub888-refused-${label}`);

  // The first field typed again: its mark alone goes.
  const typed = first.locator('input');
  await typed.fill(`${await typed.inputValue()}1`);
  await unmarked(first);
  await marked(second);
  await marked(last);
  await first.scrollIntoViewIfNeeded();
  await capture(page, `CLOSE-${window.app}-hub888-first-typed-${label}`);

  // The second one too; the last keeps its own until it is corrected or saved again.
  await second.locator('input').fill(`${await second.locator('input').inputValue()} 2`);
  await unmarked(second);
  await unmarked(first);
  await marked(last);
  await last.scrollIntoViewIfNeeded();
  await capture(page, `CLOSE-${window.app}-hub888-second-typed-${label}`);

  // Nothing reached the Hub.
  await page.unroute(window.save);
  expect(psql(window.created)).toBe('0');
}

for (const window of [ZONE, RESERVATION]) {
  for (const size of VIEWPORTS) {
    test(`hub#888 ${window.app} at ${size.label}: three fields refused with the same words lose their marks one by one`, async ({ browser }) => {
      const { context, page } = await ownerPage(browser, window.page, { width: size.width, height: size.height });
      try {
        await correctOneByOne(page, window, 'Check this field.', size.label);
      } finally {
        await context.close();
      }
    });
  }

  test(`hub#888 ${window.app} in Spanish: the window speaks Spanish and the fields lose their marks one by one`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, window.page);
    try {
      await saveSessionForTheSweep(context);
      await correctOneByOne(page, window, 'Revisa este campo.', 'es-1440');
      await expect(page.locator(`ion-modal[data-testid=${window.testid}] [data-testid=${window.testid}-cancel]`)).toHaveText('Cancelar');
    } finally {
      await context.close();
    }
  });
}

// flow: STAFF-F01, STAFF-F03 — hub#888: in a window, fields refused with the same words lose their marks one by
// one as each is corrected, a search picker (Combo of @erplora/ui) too: it hands its name to its field, so the
// window tells which refused field a choice corrects. Seen in Staff › Members › «+» at 390, 834 and 1440: the
// save is refused for the first name, the Role and the Hub user with the same words; choosing a Hub user in its
// picker takes the mark from it alone, typing the first name from it alone, and the Role keeps its own. The
// refusal is answered in the browser (`page.route`), so nothing is created. Once more in Spanish, whose session the
// fleet's visual sweep reads (`E2E_SAVE_STORAGE_STATE`).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, type Credentials, EMPLOYEE, login, psql, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { expectMarked, expectUnmarked, refuseWithTheSameWords } from './same-words-helpers';
import { stamp, VIEWPORTS } from './sale-helpers';

const LAST = `E2E888${stamp()}`;

async function signedIn(browser: Browser, viewport: { width: number; height: number }, credentials?: Credentials): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/staff/members', credentials);
  return { context, page };
}

// The employee's account exists in the hub only after their first sign-in (the SaaS creates it on the way in): the
// Hub user picker offers it then.
test.beforeAll(async ({ browser }) => {
  const employee = await signedIn(browser, VIEWPORTS[2], EMPLOYEE);
  await employee.context.close();
});

/** In Staff › Members › «+», the first name, the Role and the Hub user refused with the same `words` lose their marks
 *  one by one: a Hub user chosen in its picker, then the first name typed; the Role keeps its own. Screenshots
 *  `CLOSE-STAFF-hub888-<step>-<label>`. */
async function correctOneByOne(page: Page, words: string, label: string): Promise<void> {
  const marked = (field: Locator): Promise<void> => expectMarked(field, words);
  const unmarked = (field: Locator): Promise<void> => expectUnmarked(field, words);
  await shown(page).locator('[data-testid=staff-members-add]').click();
  const form = page.locator('ion-modal[data-testid=staff-member-form]');
  await expect(form).toBeVisible();
  const first = form.locator('[data-testid=staff-member-form-first_name]');
  const role = form.locator('[data-testid=staff-member-form-role_id]');
  const user = form.locator('[data-testid=staff-member-form-user_id]');
  await first.locator('input').fill('E2E Ana');
  await form.locator('[data-testid=staff-member-form-last_name] input').fill(LAST);

  // Saving a new member (POST `/api/staff/members`) is refused for the three, with the same words.
  await refuseWithTheSameWords(page, '**/api/staff/members', ['first_name', 'role_id', 'user_id'], words);
  await form.locator('[data-testid=staff-member-form-submit]').click();
  for (const field of [first, role, user]) await marked(field);
  await capture(page, `CLOSE-STAFF-hub888-refused-${label}`);

  // The Hub user is chosen in its picker, from the server's search: its mark alone goes.
  const typed = user.locator('input');
  await typed.click();
  await typed.fill('employee');
  await page.locator('[data-testid^=staff-member-form-user_id-option-]', { hasText: 'employee@example.com' }).first().click();
  await expect(page.locator('[data-testid^=staff-member-form-user_id-option-]')).toHaveCount(0);
  await expect(typed).toHaveValue('employee@example.com');
  await unmarked(user);
  await marked(first);
  await marked(role);
  await user.scrollIntoViewIfNeeded();
  await capture(page, `CLOSE-STAFF-hub888-user-chosen-${label}`);

  // Typing the first name takes its mark alone: the Role keeps its own until it is corrected or saved again.
  await first.locator('input').fill('E2E Bea');
  await unmarked(first);
  await marked(role);
  await unmarked(user);
  await role.scrollIntoViewIfNeeded();
  await capture(page, `CLOSE-STAFF-hub888-name-typed-${label}`);

  // Nothing reached the Hub: no member with that name.
  await page.unroute('**/api/staff/members');
  expect(psql(`select count(*) from staff_member where last_name = '${LAST}'`)).toBe('0');
}

for (const size of VIEWPORTS) {
  test(`hub#888 at ${size.label}: a picker refused with the same words as other fields loses its mark alone when another option is chosen`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, { width: size.width, height: size.height });
    try {
      await correctOneByOne(page, 'Check this field.', size.label);
    } finally {
      await context.close();
    }
  });
}

test('hub#888 in Spanish: the window speaks Spanish and the picker loses its mark alone', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, '/staff/members');
  try {
    await saveSessionForTheSweep(context);
    await correctOneByOne(page, 'Revisa este campo.', 'es-1440');
    await expect(page.locator('ion-modal[data-testid=staff-member-form] .ep-form-modal__cancel')).toHaveText('Cancelar');
  } finally {
    await context.close();
  }
});

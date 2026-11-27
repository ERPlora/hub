// flow: BASE-F130 and BASE-F128 (base/WORKBOOK.md)
// «Role in this business» on a person's page: the owner gives the employee a role of the business by choosing it, and the
// employee's open screen follows it without a reload; back to the one of their invitation, it closes again. On the owner's
// own page there is nothing to choose, and it says why. In the three sizes, in Spanish and in English, nothing cut and the
// choice reached by keyboard. Every role is the run's own, deleted after it, and the employee ends with their invitation's.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { cutLabels } from './field-labels';
import { A, api, capture, collectProblems, EMPLOYEE, horizontalOverflow, hostPage, psql, shown, testid, uniqueName } from './helpers';
import { spanishPerson } from './home-helpers';
import { toastSaying } from './toast-helpers';

const SIZES = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1280, height: 720 },
] as const;

const employeeId = () => psql(`select username from auth_user where email = '${EMPLOYEE.email}'`);
const ownerId = () => psql("select username from auth_user where email = 'owner@example.com'");
const card = (page: Page) => testid(page, 'person-role');

/** A role the owner makes from the manager's by the Hub's API; `use` runs with it, and it is deleted after. */
async function withRole(context: BrowserContext, name: string, use: (key: string) => Promise<void>): Promise<void> {
  const made = await api<{ key: string }>(context, A, 'POST', '/roles', { based_on: 'hub_manager', name });
  expect(made.status).toBe(200);
  try {
    await use(made.data.key);
  } finally {
    await api(context, A, 'POST', '/roles/assign', { person: employeeId(), role: 'hub_employee' });
    expect((await api(context, A, 'POST', '/roles/delete', { role: made.data.key })).status).toBe(200);
  }
}

/** Chooses `label` in «Role», as a person does with the popover of the select. */
async function choose(page: Page, label: string): Promise<void> {
  await card(page).locator('[data-testid="person-role-select"]').click();
  await page.locator('ion-select-popover ion-radio').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) }).click();
  await expect(page.locator('ion-select-popover')).toHaveCount(0);
}

async function snap(page: Page, name: string): Promise<void> {
  await page.mouse.move(0, 0);
  await card(page).scrollIntoViewIfNeeded();
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  expect(await cutLabels(card(page))).toEqual([]);
  await capture(page, name);
}

test('BASE-F130: the owner gives the employee a role on their page, and the employee’s open screen follows it', async ({ browser }) => {
  const employee = await hostPage(browser, A, { next: '/tax/rules', credentials: EMPLOYEE });
  const owner = await spanishPerson(browser, SIZES[2]);
  const problems = await collectProblems(owner.page);
  const name = uniqueName('Jefe de turno');
  try {
    await expect(testid(employee.page, 'no-access')).toBeVisible();
    await employee.page.evaluate(() => Object.assign(window, { e2eStillHere: true }));
    await withRole(owner.context, name, async (key) => {
      await owner.page.goto(`${A}/employees/${employeeId()}`);
      await expect(card(owner.page)).toContainText('Rol en este negocio');
      await expect(card(owner.page).locator('[data-testid="person-role-select"]')).toHaveJSProperty('value', 'hub_employee');

      await choose(owner.page, name);
      await expect(toastSaying(owner.page, new RegExp(`tiene ahora el rol ${name}\\.`))).toBeVisible();
      await expect(shown(employee.page).locator('[data-testid=tax-rules-add]')).toBeVisible();
      await expect(card(owner.page).locator('[data-testid="person-role-select"]')).toHaveJSProperty('value', key);

      await choose(owner.page, 'El de la invitación \\(Empleado\\)');
      await expect(testid(employee.page, 'no-access')).toBeVisible();
      expect(await employee.page.evaluate(() => (window as { e2eStillHere?: boolean }).e2eStillHere)).toBe(true);
    });
    expect((await problems()).console).toEqual([]);
  } finally {
    await owner.context.close();
    await employee.context.close();
  }
});

test('BASE-F130: the role is chosen with the keyboard, and a screen reader names it', async ({ browser }) => {
  const employee = await hostPage(browser, A, { credentials: EMPLOYEE });
  await employee.context.close();
  const owner = await spanishPerson(browser, SIZES[1]);
  const name = uniqueName('Cajero');
  try {
    await withRole(owner.context, name, async () => {
      await owner.page.goto(`${A}/employees/${employeeId()}`);
      const select = card(owner.page).getByRole('button', { name: /^Rol\b/ });
      await select.focus();
      await owner.page.keyboard.press('Enter');
      const option = owner.page.locator('ion-select-popover ion-radio').filter({ hasText: name });
      await expect(option).toBeVisible();
      await option.focus();
      await owner.page.keyboard.press('Space');
      await expect(toastSaying(owner.page, new RegExp(`tiene ahora el rol ${name}\\.`))).toBeVisible();
    });
  } finally {
    await owner.context.close();
  }
});

for (const size of SIZES) {
  test(`BASE-F130: the person's page with «Role in this business», in Spanish and English, at ${size.width}`, async ({ browser }) => {
    const signedIn = await hostPage(browser, A, { credentials: EMPLOYEE });
    await signedIn.context.close();
    const spanish = await spanishPerson(browser, size);
    const english = await hostPage(browser, A, { viewport: size });
    try {
      await withRole(spanish.context, uniqueName('Cajero'), async () => {
        for (const [language, { page }] of [['es', spanish], ['en', english]] as const) {
          await page.goto(`${A}/employees/${employeeId()}`);
          await expect(card(page).locator('[data-testid="person-role-select"]')).toBeVisible();
          await snap(page, `BASE-F130-person-role-${language}-${size.width}`);

          await page.goto(`${A}/employees/${ownerId()}`);
          await expect(card(page).locator('[data-testid="person-role-refused"]')).toBeVisible();
          await expect(card(page).locator('[data-testid="person-role-select"]')).toHaveCount(0);
          await snap(page, `BASE-F130-person-role-owner-${language}-${size.width}`);
        }
      });
    } finally {
      await spanish.context.close();
      await english.context.close();
    }
  });
}

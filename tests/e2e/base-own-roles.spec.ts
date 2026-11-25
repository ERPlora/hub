// flow: BASE-F127, BASE-F128, BASE-F129 and BASE-F131
// The business's own roles on screen: the owner duplicates the employee's in Employees › Roles, adjusts what it allows and
// deletes it; one somebody has is not deleted; one left to review is saved as it is; and nobody lets a role do more than
// they may do themselves. Every role is the run's own, deleted after it.
import { type Browser, expect, type Locator, type Page, test, type ViewportSize } from '@playwright/test';

import { cutLabels } from './field-labels';
import { A, api, capture, collectProblems, EMPLOYEE, horizontalOverflow, hostPage, psql, shown, uniqueName } from './helpers';
import { spanishPerson } from './home-helpers';
import { rowAction } from './service-helpers';

const SIZES = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1280, height: 720 },
] as const;
const ROLES = '/employees#roles';

interface Role {
  key: string;
  label: string;
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const rows = (page: Page) => shown(page).locator('[data-testid="roles-row"], [data-testid="roles-card"]');
const named = (page: Page, name: string) => rows(page).filter({ hasText: name });
const modal = (page: Page, id: string) => page.locator(`ion-modal[data-testid="${id}"]:not(.overlay-hidden)`);
/** The choices of the three states whose text is cut, or which go past their strip (none should). */
const cutChoices = (form: Locator) =>
  form.locator('ion-segment').evaluateAll((strips) =>
    strips.flatMap((strip) => {
      const cut = [...strip.querySelectorAll('ion-label')].some((label) => label.scrollWidth > label.clientWidth);
      return cut || strip.scrollWidth > strip.clientWidth ? [`${strip.getAttribute('data-testid')}: ${strip.scrollWidth} in ${strip.clientWidth}, ${[...strip.querySelectorAll('ion-segment-button')].map((b) => b.getBoundingClientRect().width.toFixed(1))}, ${[...strip.querySelectorAll('ion-label')].map((b) => b.scrollWidth)}`] : [];
    }),
  );
const isOn = (toggle: Locator) => toggle.evaluate((el) => (el as HTMLIonToggleElement).checked);

async function snap(page: Page, name: string, width: number, flow = 'BASE-F128'): Promise<void> {
  await page.mouse.move(0, 0);
  expect(await horizontalOverflow(page), `${name} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `${flow}-${name}-${width}`);
}

/** What the role does with each permission, as the Hub answers it. */
async function states(page: Page, role: string): Promise<Record<string, string>> {
  const answer = await api<{ apps: { permissions: { permission: string; state: string }[] }[] }>(
    page.context(),
    A,
    'GET',
    `/roles/detail?role=${role}`,
  );
  return Object.fromEntries(answer.data.apps.flatMap((app) => app.permissions.map((line) => [line.permission, line.state])));
}

/** A role the owner makes by the Hub's API, deleted after `use`. */
async function withRole(page: Page, name: string, use: (role: Role) => Promise<void>, basedOn = 'hub_employee'): Promise<void> {
  const made = await api<Role>(page.context(), A, 'POST', '/roles', { based_on: basedOn, name: uniqueName(name) });
  expect(made.status).toBe(200);
  try {
    await use(made.data);
  } finally {
    await api(page.context(), A, 'POST', '/roles/delete', { role: made.data.key });
  }
}

/** Who may be given a role: the employee, who exists in the business once they have signed in. */
async function employeeOf(browser: Browser): Promise<string> {
  const { context } = await hostPage(browser, A, { credentials: EMPLOYEE });
  await context.close();
  return psql(`select username from auth_user where email = '${EMPLOYEE.email}'`);
}

/** Employees › Roles as the owner opens it in Spanish. */
async function ownerRoles(browser: Browser, viewport: ViewportSize) {
  const { context, page } = await spanishPerson(browser, viewport);
  await page.goto(`${A}${ROLES}`);
  await expect(rows(page)).toHaveCount(5);
  return { context, page };
}

for (const size of SIZES) {
  test(`BASE-F127 BASE-F128 BASE-F129: the owner duplicates a role, adjusts it, sees it listed and deletes it at ${size.width}`, async ({ browser }) => {
    const { context, page } = await ownerRoles(browser, size);
    const problems = await collectProblems(page);
    const name = uniqueName('Cajero');
    await snap(page, 'list', size.width, 'BASE-F82');
    let key = '';
    try {
      // «Duplicar» on Empleado.
      await rowAction(page, 'roles', 'hub_employee', 'duplicate');
      const form = modal(page, 'role-new');
      await expect(form.locator('[data-testid="role-new-based-on"]')).toContainText('Empleado');
      await form.locator('[data-testid="role-new-name"] input').fill(name);
      expect(await cutLabels(form)).toEqual([]);
      await snap(page, 'new', size.width, 'BASE-F127');
      await form.locator('[data-testid="role-new-submit"]').click();

      // It opens to adjust it.
      await expect(page).toHaveURL(/\/employees\/roles\/[0-9a-f-]{36}$/);
      key = page.url().split('/').at(-1)!;
      await expect(testid(page, 'role-app-sensitive')).toContainText('Datos sensibles');
      expect(await cutLabels(testid(page, 'role-form'))).toEqual([]);
      expect(await cutChoices(testid(page, 'role-form'))).toEqual([]);
      expect(await isOn(testid(page, 'role-switch-sale.take_payment'))).toBe(true);
      await expect(testid(page, 'role-review')).toHaveCount(0);
      await snap(page, 'editor-top', size.width);

      await testid(page, 'role-switch-sale.take_payment').click();
      const voids = testid(page, 'role-states-sale.void_sale');
      await voids.scrollIntoViewIfNeeded();
      await voids.locator('ion-segment-button').filter({ hasText: /^No$/ }).click();
      await snap(page, 'editor-sale', size.width);
      await testid(page, 'role-save').scrollIntoViewIfNeeded();
      await testid(page, 'role-save').click();
      await expect(testid(page, 'role-saved')).toContainText('Rol guardado.');
      await snap(page, 'editor-saved', size.width);
      expect(await states(page, key)).toMatchObject({ 'sale.take_payment': 'off', 'sale.void_sale': 'off', 'sale.view_sale': 'on' });

      // And it is in the list.
      await page.goto(`${A}${ROLES}`);
      await expect(rows(page)).toHaveCount(6);
      await expect(named(page, name)).toContainText('Propio');
      await snap(page, 'list-own', size.width, 'BASE-F82');

      await rowAction(page, 'roles', key, 'edit');
      await expect(testid(page, 'role-switch-sale.take_payment')).toBeVisible();
      expect(await isOn(testid(page, 'role-switch-sale.take_payment'))).toBe(false);
      await page.goto(`${A}${ROLES}`);

      await rowAction(page, 'roles', key, 'delete');
      const question = modal(page, 'role-delete');
      await expect(question).toContainText(`¿Borrar el rol ${name}? No se puede deshacer.`);
      await snap(page, 'delete', size.width, 'BASE-F129');
      await question.locator('[data-testid="role-delete-submit"]').click();
      await expect(rows(page)).toHaveCount(5);
      key = '';
    } finally {
      if (key) await api(context, A, 'POST', '/roles/delete', { role: key });
    }
    const seen = await problems();
    expect(seen.console).toEqual([]);
    expect(seen.page).toEqual([]);
    await context.close();
  });

  test(`BASE-F129: a role somebody has is not deleted, and the question says why at ${size.width}`, async ({ browser }) => {
    const person = await employeeOf(browser);
    const { context, page } = await ownerRoles(browser, size);
    const give = (role: string) => api(context, A, 'POST', '/roles/assign', { person, role });
    await withRole(page, 'Cajero', async (role) => {
      expect((await give(role.key)).status).toBe(200);
      try {
        await expect(named(page, role.label)).toContainText('1');
        await rowAction(page, 'roles', role.key, 'delete');
        const question = modal(page, 'role-delete');
        await question.locator('[data-testid="role-delete-submit"]').click();
        await expect(question).toContainText('1 persona tiene este rol. Dale otro antes de borrarlo.');
        await snap(page, 'in-use', size.width, 'BASE-F129');
        await question.locator('[data-testid="role-delete-cancel"]').click();
        await expect(named(page, role.label)).toHaveCount(1);
      } finally {
        expect((await give('hub_employee')).status).toBe(200);
      }
    });
    await context.close();
  });

  test(`BASE-F131: a role left to review says which permissions are new and is reviewed by saving it at ${size.width}`, async ({ browser }) => {
    const { context, page } = await ownerRoles(browser, size);
    await withRole(page, 'Cajero', async (role) => {
      psql(`update base_businessrole set states = states - 'sale.void_sale' where id = '${role.key}'`);
      expect((await api(context, A, 'POST', '/roles/update', { role: role.key, description: 'La caja' })).status).toBe(200);
      const pill = named(page, role.label).locator('[data-testid="roles-to-review"]');
      await expect(pill).toHaveText('Por revisar');
      await snap(page, 'list', size.width, 'BASE-F131');

      await named(page, role.label).click();
      await expect(testid(page, 'role-review')).toContainText('Permisos nuevos por revisar');
      await expect(testid(page, 'role-to-review')).toHaveCount(1);
      await expect(testid(page, 'role-permission-sale.void_sale')).toContainText('Por revisar');
      await snap(page, 'editor', size.width, 'BASE-F131');
      await testid(page, 'role-to-review').scrollIntoViewIfNeeded();
      await snap(page, 'editor-marked', size.width, 'BASE-F131');
      await testid(page, 'role-save').click();
      await expect(testid(page, 'role-saved')).toBeVisible();
      await expect(testid(page, 'role-review')).toHaveCount(0);
      await expect(testid(page, 'role-to-review')).toHaveCount(0);
      expect(await states(page, role.key)).toMatchObject({ 'sale.void_sale': 'off', 'sale.take_payment': 'on' });

      await page.goto(`${A}${ROLES}`);
      await expect(named(page, role.label)).toBeVisible();
      await expect(pill).toHaveCount(0);
    });
    await context.close();
  });

  test(`BASE-F128: nobody lets a role do more than they may do themselves, said next to «Save» at ${size.width}`, async ({ browser }) => {
    const person = await employeeOf(browser);
    const { context, page } = await ownerRoles(browser, size);
    const give = (role: string) => api(context, A, 'POST', '/roles/assign', { person, role });
    await withRole(page, 'Cajero', async (role) => {
      await withRole(
        page,
        'Jefe de turno',
        async (lead) => {
          const without = { role: lead.key, states: { 'base.view_costs': 'off' } };
          expect((await api(context, A, 'POST', '/roles/update', without)).status).toBe(200);
          expect((await give(lead.key)).status).toBe(200);
          try {
            const editor = await hostPage(browser, A, { viewport: size, credentials: EMPLOYEE, next: `/employees/roles/${role.key}` });
            const costs = testid(editor.page, 'role-switch-base.view_costs');
            await costs.scrollIntoViewIfNeeded();
            await costs.click();
            await testid(editor.page, 'role-save').click();
            await expect(testid(editor.page, 'role-save-error')).toContainText('A role may not allow more than you may do yourself.');
            await snap(editor.page, 'beyond', size.width);
            expect(await states(page, role.key)).toMatchObject({ 'base.view_costs': 'off' });
            await editor.context.close();
          } finally {
            expect((await give('hub_employee')).status).toBe(200);
          }
        },
        'hub_admin',
      );
    });
    await context.close();
  });
}

test('BASE-F82: whoever does not manage the roles is shown them, with nothing to change', async ({ browser }) => {
  const { context, page } = await hostPage(browser, A, { credentials: EMPLOYEE, next: ROLES });
  await expect(rows(page)).toHaveCount(5);
  await expect(testid(page, 'roles-add')).toHaveCount(0);
  await expect(shown(page).locator('[data-testid$="-duplicate"], [data-testid$="-menu"][data-testid^="roles-row"]')).toHaveCount(0);
  await context.close();
});
